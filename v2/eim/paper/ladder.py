"""Protección progresiva de ganancias (PPP): SL dinámico por escalones de beneficio neto.

Reglas (deterministas; ningún agente las toca una vez abierta la posición):
- Fase A: manda el SL inicial (el de la idea, dimensionado por riesgo).
- Fase B: cuando el beneficio NETO estimado máximo llega al primer escalón se activa la
  protección y el SL pasa al precio cuyo neto es ese nivel; cada incremento más de beneficio
  máximo sube un escalón. El par (primer escalón, incremento) lo resuelve `LadderParams.steps`
  con el riesgo de ESA operación: fijo en USDT (control) o como fracción del riesgo (◆6 de T106).
  Sin TP final y sin cierre por tiempo: solo cierra el SL vigente. La protección nunca baja, ni
  vuelve a la entrada.
- BE+ conviviendo (◆3 de T106, `be_with_ladder`, solo en `ExecParams.be_timeframes`): si el precio
  avanza `be_trigger_r` R, desde la vela siguiente el SL candidato del BE+ es entrada +
  `be_lock_r` R + costo estimado (como en `engine.simulate`). El SL vigente es el MEJOR de los dos
  candidatos y solo se mueve si sube; el cierre por un SL movido por cualquiera de los dos es
  «SLD» (stop dinámico) y el historial dice de dónde vino (`source`: «escalon» o «be»).
- El SL de cada nivel es el precio cuyo beneficio NETO estimado es ese nivel (fórmulas en
  `ladder_math.py`, misma contabilidad que `engine.Outcome.net`).
- Camino de 15 m, sin anticipación y conservador: en cada vela primero se comprueba el SL vigente
  AL ABRIR la vela (un hueco más allá se ejecuta a la apertura); el avance de esa vela solo sube
  el SL desde la vela SIGUIENTE (no se sabe si el extremo llegó antes o después del retroceso).
  Las velas AMBIGUAS (las que pueden subir el SL y volver a tocarlo) se resuelven con las velas
  de 1 min en su orden real, aplicando la misma regla dentro de cada minuto; sin esos datos se
  queda la regla conservadora.
  Si una vela cruza varios escalones se aplica el último confirmado por su extremo.
- Estimado vs realizado: el SL se calcula con una RESERVA: el mayor deslizamiento de las últimas
  `slip_lookback` velas (datos ya conocidos) y `funding_reserve` liquidaciones futuras de funding;
  al salir se cobra el de la vela real y el funding hasta ese
  momento, así que el neto realizado puede diferir del nominal (hueco, vela más ancha).
- Datos no finitos en una vela = incidencia técnica: la posición queda ABIERTA marcada
  «incidencia», sin cierre inventado.
- Suelo guardado (T110, `ladder_floor.py`): si el diario guardó un SL mejor que el recalculado, se
  adopta desde el instante en que se confirmó; si lo guardado no deja reconstruirla, la operación
  queda «inconsistente», abierta y sin cierre inventado.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import NamedTuple

import numpy as np

from eim.paper.engine import Outcome, Path, _funding, _limit_fill, _slip, _stop_exit, _with_r
from eim.paper.ideas import Idea
from eim.paper.ladder_floor import Guard, adopt, arm, early, finish, settle_close
from eim.paper.ladder_math import (  # noqa: F401  (reexportadas: tests y `ladder_book`)
    EPS,
    LadderCosts,
    costs_for,
    floor_qty,
    level_of,
    net_usd,
    nominal,
    protect_price,
)
from eim.paper.params import ExecParams, LadderParams, SymbolSpec


def _entry(idea: Idea, path: Path, ep: ExecParams) -> tuple[str, int, int, float, float, float]:
    """('ok'|'pending'|'cancel'|'expired', k, start, fill, fee_in, slip_in).

    La entrada a mercado paga el MISMO deslizamiento de entrada que la sombra (`engine.simulate`,
    calibrado con el libro real); antes pagaba el de salida y sesgaba el A/B de T111 en contra de
    la escalera (BACKLOG T109 (1))."""
    s, cp = idea.side, ep.costs
    j0 = int(np.searchsorted(path.t, idea.t))
    if j0 >= len(path.t):
        return "pending", 0, 0, 0.0, 0.0, 0.0
    if idea.kind == "market":
        slip = _slip(path, j0, ep, entry=True)
        return "ok", j0, j0, float(path.o[j0]) * (1 + s * slip), cp.taker_fee, slip
    what, k = _limit_fill(idea, path, j0)
    if what == "fill":
        return "ok", int(k), int(k) + 1, idea.entry, cp.maker_fee, 0.0
    return ("pending" if what == "pending" else "cancel" if what == "cancel_tp" else "expired",
            int(k or 0), 0, 0.0, 0.0, 0.0)


class _Step(NamedTuple):
    """Lo que una vela (o un minuto) haría con la protección; `_Run.peek` no muta nada."""

    max_float: float
    level: int
    stop: float | None        # nuevo SL (solo si sube) o None
    source: str               # «escalon» | «be» | «»
    nominal: float            # neto protegido estimado del nuevo SL
    be_armed: bool            # el precio llegó al disparo del BE+


class _Run:
    """Estado vivo de la escalera: SL vigente, escalón, máximo flotante, BE+ e historial."""

    def __init__(self, s: int, qty: float, fill: float, c: LadderCosts, stop: float,
                 first: float, step: float, tick: float,
                 be: tuple[float, float] | None = None) -> None:
        self.s, self.qty, self.fill, self.c0 = s, qty, fill, c
        self.first, self.step_usd, self.tick = first, step, tick
        self.stop, self.level, self.max_float, self.hist, self.c_stop = stop, 0, -math.inf, [], c
        self.be, self.be_armed, self.source = be, False, "inicial"   # be = (disparo, SL del BE+)
        self.floor, self.floor_due, self.recovered = None, False, None  # suelo guardado (T110)

    @property
    def protected(self) -> bool:
        """¿El SL ya se movió desde el inicial (por un escalón o por el BE+)?"""
        return bool(self.hist)

    def _up(self, p: float, fav: float) -> bool:
        """Solo sube (demostrado) y el precio ya lo alcanzó."""
        return (p - self.stop) * self.s > 0 and (fav - p) * self.s >= 0

    def peek(self, fav: float, fund: float, cj: LadderCosts) -> _Step:
        """Qué pasaría si el precio llegara a `fav`: el nuevo SL es el MEJOR candidato (◆3)."""
        s = self.s
        mf = max(self.max_float, net_usd(s, self.qty, self.fill, fav, fund, cj))
        new = level_of(mf, self.first, self.step_usd)
        best = _Step(mf, self.level, None, "", 0.0, False)
        if new > self.level:
            lv = nominal(new, self.first, self.step_usd)
            p = protect_price(s, self.qty, self.fill, lv, fund, cj, self.tick)
            if self._up(p, fav):
                best = _Step(mf, new, p, "escalon", lv, False)
        armed = self.be is not None and (fav - self.be[0]) * s >= 0
        if armed and not self.be_armed:
            lock = self.be[1]
            if self._up(lock, fav) and (best.stop is None or (lock - best.stop) * s > 0):
                best = _Step(mf, self.level, lock, "be",
                             net_usd(s, self.qty, self.fill, lock, fund, cj), False)
        return best._replace(be_armed=armed)

    def apply(self, got: _Step, end: int, cj: LadderCosts) -> None:
        self.max_float = got.max_float
        self.be_armed = self.be_armed or got.be_armed
        if got.stop is not None:
            self.stop, self.level, self.c_stop, self.source = got.stop, got.level, cj, got.source
            self.hist.append({"t": end, "level": got.level, "nominal": got.nominal,
                              "stop": got.stop, "max_float": self.max_float,
                              "source": got.source})


def _sub_bars(run: _Run, fine: Path, path: Path, ep: ExecParams, fill_t: int, t0: int, step: int,
              cj: LadderCosts, reserve: float) -> tuple[str, float, int] | None:
    """Recorre las velas finas de una vela gruesa ambigua, en orden real: en cada una manda el SL
    vigente al abrirla y el avance sube el SL desde la siguiente. (motivo, precio, t) si cierra."""
    a, b = int(np.searchsorted(fine.t, t0)), int(np.searchsorted(fine.t, t0 + step))
    s = run.s
    for m in range(a, b):
        o, h, lo = float(fine.o[m]), float(fine.h[m]), float(fine.l[m])
        end = int(fine.t[m]) + fine.step
        adopt(run, int(fine.t[m]))
        if (lo <= run.stop) if s > 0 else (h >= run.stop):
            gap = (o <= run.stop) if s > 0 else (o >= run.stop)
            return ("SLD" if run.protected else "SL"), (o if gap else run.stop), end
        fund = _funding(path, s, fill_t, end, ep)[0] + reserve
        run.apply(run.peek(h if s > 0 else lo, fund, cj), end, cj)
    return None


def _be_levels(idea: Idea, fill: float, risk: float, ep: ExecParams, lp: LadderParams,
               tick: float) -> tuple[float, float] | None:
    """(precio de disparo, SL bloqueado) del BE+ de T48b cuando convive con la escalera (◆3) en
    el marco de la idea; None si no aplica. El SL se redondea al tick a favor de la protección."""
    if not (lp.be_with_ladder and ep.be_trigger_r > 0 and idea.timeframe in ep.be_timeframes):
        return None
    s = idea.side
    lock_r = ep.be_lock_r + (ep.est_cost_frac * fill / risk if ep.be_cover_costs else 0.0)
    lock = fill + s * lock_r * risk
    n = math.ceil(lock / tick - EPS) if s > 0 else math.floor(lock / tick + EPS)
    return fill + s * ep.be_trigger_r * risk, round(n * tick, 8)


def _fine_covers(fine: Path | None, t0: int, step: int) -> bool:
    """¿Hay velas finas completas y válidas para toda la vela gruesa [t0, t0+step)?"""
    if fine is None or not len(fine.t):
        return False
    a, b = int(np.searchsorted(fine.t, t0)), int(np.searchsorted(fine.t, t0 + step))
    if b - a != step // fine.step:
        return False
    return bool(np.isfinite(fine.o[a:b]).all() and np.isfinite(fine.h[a:b]).all()
                and np.isfinite(fine.l[a:b]).all())


def simulate_ladder(idea: Idea, path: Path, ep: ExecParams, lp: LadderParams, qty: float,
                    fine: Path | None = None, *, spec: SymbolSpec,
                    guard: Guard | None = None) -> Outcome:
    """Simula la operación con SL inicial y escalera de protección (sin TP ni tiempo).

    `spec` es la ficha del instrumento (tick del símbolo, T108): el SL se redondea con el tick de
    SU símbolo, nunca con el de otro. Los escalones se resuelven para ESTA operación con
    `lp.steps(riesgo en USDT)`, así que con `basis="r"` dependen del riesgo realmente abierto.
    `fine` (velas de 1 min) resuelve el orden real de los precios SOLO en las velas de 15 m
    ambiguas (las que pueden subir el SL y volver a tocarlo); sin datos finos se usa la regla
    conservadora descrita arriba. `guard` (T110) es lo que el diario guardó de esta operación:
    suelo del SL y, si lo hay, el motivo de su estado inconsistente.
    """
    s = idea.side
    what, k, start, fill, fee_in, slip_in = _entry(idea, path, ep)
    if what == "pending":
        return Outcome(idea, "PENDIENTE")
    if what == "expired":
        return Outcome(idea, "CANCELADA", "NO_LLENADA", exit_t=idea.t + idea.fill_ms)
    if what == "cancel":
        return Outcome(idea, "CANCELADA", "OBJETIVO_SIN_LLENAR",
                       exit_t=int(path.t[k]) + path.step)
    fill_t = int(path.t[k])
    if (fill - idea.sl) * s <= ep.min_risk_frac * fill:
        return Outcome(idea, "RECHAZADA", "GEOMETRIA", exit_t=fill_t, fill=fill)
    risk = abs(fill - idea.sl)
    first, step_usd = lp.steps(qty * risk)        # escalones de ESTA operación (◆6: en R o fijos)
    be = _be_levels(idea, fill, risk, ep, lp, spec.tick)
    run = _Run(s, qty, fill, costs_for(fee_in, slip_in, ep), idea.sl, first, step_usd, spec.tick,
               be)
    hold = arm(run, guard, spec.tick)          # estado inconsistente: no se cierra sola (T110)
    reserve = max(0.0, s * ep.funding_8h_assumed) * lp.funding_reserve   # reserva de funding
    incident, fine_bars = "", 0
    reason, ex, jx, ex_t, last_ok = "", None, None, None, k
    if start > k and ((path.l[k] <= idea.sl) if s > 0 else (path.h[k] >= idea.sl)) and not (
            hold := hold or early(run, int(path.t[k]) + path.step)):
        reason, ex, jx = "SL", idea.sl, k                # límite llenada y SL en la misma vela
    else:
        for j in range(start, len(path.t)):
            o, h, lo, cl = float(path.o[j]), float(path.h[j]), float(path.l[j]), float(path.c[j])
            if not all(math.isfinite(x) for x in (o, h, lo, cl)):
                incident = f"vela sin datos válidos en t={int(path.t[j])}"
                break
            last_ok = j
            t0 = int(path.t[j])
            end = t0 + path.step
            adopt(run, t0)
            fav = h if s > 0 else lo
            fund = _funding(path, s, fill_t, end, ep)[0] + reserve
            slip = max(_slip(path, x, ep) for x in range(max(start, j - lp.slip_lookback + 1),
                                                         j + 1))
            cj = replace(run.c0, slip_out=slip)               # deslizamiento esperado (reserva)
            got = run.peek(fav, fund, cj)
            if not hold and got.stop is not None and _fine_covers(fine, t0, path.step) and (
                    (lo <= got.stop) if s > 0 else (h >= got.stop)):
                fine_bars += 1                                # ambigua: se resuelve con 1 min
                hit = _sub_bars(run, fine, path, ep, fill_t, t0, path.step, cj, reserve)
                if hit and not (hold := early(run, hit[2])):
                    reason, ex, ex_t = hit
                    jx = j
                    break
                continue
            if ((lo <= run.stop) if s > 0 else (h >= run.stop)) and not (   # SL vigente AL ABRIR
                    hold := hold or early(run, end)):
                reason, ex, jx = ("SLD" if run.protected else "SL"), _stop_exit(
                    path, s, j, run.stop, k), j
                break
            run.apply(got, end, cj)
    if reason:
        reason, ex, held = settle_close(run, reason, ex, float(path.l[jx]), float(path.h[jx]))
        if held:                                     # sin cierre inventado: sigue abierta
            hold, last_ok, jx, ex_t = held, jx, None, None
    end_i = jx if jx is not None else last_ok
    if not reason:
        hold = hold or finish(run, int(path.t[end_i]) + path.step)
    hi, lo = float(path.h[k:end_i + 1].max()), float(path.l[k:end_i + 1].min())
    mfe = max(0.0, ((hi if s > 0 else lo) - fill) * s) / risk
    mae = max(0.0, (fill - (lo if s > 0 else hi)) * s) / risk
    info = {"qty": qty, "level": run.level,
            "nominal_usd": nominal(run.level, first, step_usd),
            "first_usd": first, "step_usd": step_usd,
            "max_float_usd": None if run.max_float == -math.inf else run.max_float,
            "stop": run.stop, "initial_sl": idea.sl, "stop_history": run.hist,
            "incident": incident,
            "levels": [h_["nominal"] for h_ in run.hist if h_["source"] == "escalon"],
            "stop_source": run.source,
            "be": None if be is None else {"trigger": be[0], "lock": be[1],
                                           "armed": run.be_armed},
            "last_bar_t": int(path.t[end_i]) + path.step, "fine_resolved_bars": fine_bars,
            "recovered": run.recovered, "inconsistent": hold or None}
    if reason:
        exit_t = ex_t if ex_t is not None else int(path.t[jx]) + path.step
        fund, assumed = _funding(path, s, fill_t, exit_t, ep)
        fee_out = ep.costs.taker_fee * ex / fill
        info |= {"state": "cerrada_sl_dinamico" if run.protected else "cerrada_sl_inicial",
                 "protected_est_usd": (net_usd(s, qty, fill, run.stop, fund, run.c_stop)
                                       if run.protected else None),
                 "elapsed_ms": exit_t - fill_t}
        return _with_r(Outcome(idea, "CERRADA", reason, fill_t, fill, exit_t, ex, fee_in, fee_out,
                               slip_in + _slip(path, jx, ep), fund, assumed,
                               s * (ex - fill) / fill, None, mfe, mae, ladder=info))
    mark = float(path.c[end_i])
    fund, assumed = _funding(path, s, fill_t, int(path.t[end_i]) + path.step, ep)
    info |= {"state": "inconsistente" if hold else "incidencia" if incident
             else "protegida" if run.protected else "inicial",
             "float_usd": net_usd(s, qty, fill, mark, fund, run.c0),
             "elapsed_ms": int(path.t[end_i]) + path.step - fill_t}
    return _with_r(Outcome(idea, "ABIERTA", "", fill_t, fill, None, None, fee_in, 0.0, slip_in,
                           fund, assumed, s * (mark - fill) / fill, None, mfe, mae, mark,
                           ladder=info))
