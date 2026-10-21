"""Protección progresiva de ganancias (perfil PPP): SL dinámico por escalones de beneficio neto.

Reglas (deterministas; ningún agente las toca una vez abierta la posición):
- Fase A: manda el SL inicial (el de la idea, dimensionado por riesgo).
- Fase B: cuando el beneficio NETO estimado máximo llega a `first_usdt` (10) se activa la
  protección y el SL pasa al precio cuyo neto es ese nivel; cada `step_usdt` (5) más de beneficio
  máximo sube un escalón (10, 15, 20, …). Sin TP final y sin cierre por tiempo: solo cierra el
  SL vigente. La protección nunca baja, ni vuelve a la entrada.
- Beneficio neto estimado de salir a un precio `p` (misma contabilidad que `engine.Outcome.net`,
  en USDT con `qty` BTC y entrada `f`):
      neto(p) = qty·(lado·(p − f) − fee_sal·p) − qty·f·(fee_ent + desl_ent + desl_sal + funding)
  Precio de protección del nivel L (despeje exacto; luego se redondea al tick EN CONTRA del
  operador —largo arriba, corto abajo— y se vuelve a comprobar `neto ≥ L`):
      largo : p = (L/qty + f·(1+K)) / (1 − fee_sal)       K = fee_ent+desl_ent+desl_sal+funding
      corto : p = (f·(1−K) − L/qty) / (1 + fee_sal)
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
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from eim.paper.engine import Outcome, Path, _funding, _limit_fill, _slip, _stop_exit, _with_r
from eim.paper.ideas import Idea
from eim.paper.params import ExecParams, LadderParams

EPS = 1e-9


@dataclass(frozen=True)
class LadderCosts:
    """Costos de entrada (ya conocidos) y de salida a SL (estimados), como fracciones."""

    fee_in: float
    slip_in: float
    fee_out: float
    slip_out: float


def net_usd(side: int, qty: float, fill: float, price: float, funding: float,
            c: LadderCosts) -> float:
    """Beneficio neto (USDT) de cerrar `qty` a `price`, con todos los costos modelados."""
    k = c.fee_in + c.slip_in + c.slip_out + funding
    return qty * (side * (price - fill) - c.fee_out * price) - qty * fill * k


def protect_price(side: int, qty: float, fill: float, level: float, funding: float,
                  c: LadderCosts, tick: float) -> float:
    """Precio de SL cuyo neto estimado es `level` USDT, redondeado al tick y verificado."""
    k = c.fee_in + c.slip_in + c.slip_out + funding
    if side > 0:
        exact = (level / qty + fill * (1 + k)) / (1 - c.fee_out)
        n = math.ceil(exact / tick - EPS)
    else:
        exact = (fill * (1 - k) - level / qty) / (1 + c.fee_out)
        n = math.floor(exact / tick + EPS)
    for _ in range(5):                       # el redondeo nunca puede dejar el neto bajo el nivel
        price = round(n * tick, 8)
        if net_usd(side, qty, fill, price, funding, c) >= level - EPS:
            return price
        n += side
    return round(n * tick, 8)


def level_of(max_float: float, lp: LadderParams) -> int:
    """Escalón confirmado por el beneficio neto máximo (0 = aún sin protección)."""
    if max_float + EPS < lp.first_usdt:
        return 0
    return 1 + int(math.floor((max_float - lp.first_usdt) / lp.step_usdt + EPS))


def nominal(level: int, lp: LadderParams) -> float:
    """Beneficio neto nominal protegido por un escalón (10, 15, 20, …)."""
    return lp.first_usdt + (level - 1) * lp.step_usdt if level > 0 else 0.0


def floor_qty(qty: float, lp: LadderParams) -> float:
    return math.floor(qty / lp.qty_step + EPS) * lp.qty_step


def costs_for(fee_in: float, slip_in: float, ep: ExecParams) -> LadderCosts:
    cp = ep.costs
    return LadderCosts(fee_in, slip_in, cp.taker_fee, cp.slip_base_bps / 1e4)


def _entry(idea: Idea, path: Path, ep: ExecParams) -> tuple[str, int, int, float, float, float]:
    """('ok'|'pending'|'cancel'|'expired', k, start, fill, fee_in, slip_in)."""
    s, cp = idea.side, ep.costs
    j0 = int(np.searchsorted(path.t, idea.t))
    if j0 >= len(path.t):
        return "pending", 0, 0, 0.0, 0.0, 0.0
    if idea.kind == "market":
        slip = _slip(path, j0, ep)
        return "ok", j0, j0, float(path.o[j0]) * (1 + s * slip), cp.taker_fee, slip
    what, k = _limit_fill(idea, path, j0)
    if what == "fill":
        return "ok", int(k), int(k) + 1, idea.entry, cp.maker_fee, 0.0
    return ("pending" if what == "pending" else "cancel" if what == "cancel_tp" else "expired",
            int(k or 0), 0, 0.0, 0.0, 0.0)


class _Run:
    """Estado vivo de la escalera: SL vigente, escalón, máximo flotante e historial."""

    def __init__(self, s: int, qty: float, fill: float, c: LadderCosts, stop: float,
                 lp: LadderParams) -> None:
        self.s, self.qty, self.fill, self.c0, self.lp = s, qty, fill, c, lp
        self.stop, self.level, self.max_float, self.hist, self.c_stop = stop, 0, -math.inf, [], c

    def peek(self, fav: float, fund: float, cj: LadderCosts) -> tuple[float, int, float | None]:
        """(máx. flotante, escalón, nuevo SL o None) si el precio llegara a `fav`; no muta."""
        mf = max(self.max_float, net_usd(self.s, self.qty, self.fill, fav, fund, cj))
        new = level_of(mf, self.lp)
        if new <= self.level:
            return mf, self.level, None
        p = protect_price(self.s, self.qty, self.fill, nominal(new, self.lp), fund, cj,
                          self.lp.tick)
        ok = (p - self.stop) * self.s > 0 and (fav - p) * self.s >= 0   # solo sube, demostrado
        return mf, new, p if ok else None

    def apply(self, got: tuple[float, int, float | None], end: int, cj: LadderCosts) -> None:
        self.max_float, new, p = got
        if p is not None:
            self.stop, self.level, self.c_stop = p, new, cj
            self.hist.append({"t": end, "level": new, "nominal": nominal(new, self.lp),
                              "stop": p, "max_float": self.max_float})


def _sub_bars(run: _Run, fine: Path, path: Path, ep: ExecParams, fill_t: int, t0: int, step: int,
              cj: LadderCosts, reserve: float) -> tuple[str, float, int] | None:
    """Recorre las velas finas de una vela gruesa ambigua, en orden real: en cada una manda el SL
    vigente al abrirla y el avance sube el SL desde la siguiente. (motivo, precio, t) si cierra."""
    a, b = int(np.searchsorted(fine.t, t0)), int(np.searchsorted(fine.t, t0 + step))
    s = run.s
    for m in range(a, b):
        o, h, lo = float(fine.o[m]), float(fine.h[m]), float(fine.l[m])
        end = int(fine.t[m]) + fine.step
        if (lo <= run.stop) if s > 0 else (h >= run.stop):
            gap = (o <= run.stop) if s > 0 else (o >= run.stop)
            return ("SLD" if run.level else "SL"), (o if gap else run.stop), end
        fund = _funding(path, s, fill_t, end, ep)[0] + reserve
        run.apply(run.peek(h if s > 0 else lo, fund, cj), end, cj)
    return None


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
                    fine: Path | None = None) -> Outcome:
    """Simula la operación con SL inicial y escalera de protección (sin TP ni tiempo).

    `fine` (velas de 1 min) resuelve el orden real de los precios SOLO en las velas de 15 m
    ambiguas (las que pueden subir el SL y volver a tocarlo); sin datos finos se usa la regla
    conservadora descrita arriba.
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
    run = _Run(s, qty, fill, costs_for(fee_in, slip_in, ep), idea.sl, lp)
    reserve = max(0.0, s * ep.funding_8h_assumed) * lp.funding_reserve   # reserva de funding
    incident, fine_bars = "", 0
    reason, ex, jx, ex_t, last_ok = "", None, None, None, k
    if start > k and ((path.l[k] <= idea.sl) if s > 0 else (path.h[k] >= idea.sl)):
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
            fav = h if s > 0 else lo
            fund = _funding(path, s, fill_t, end, ep)[0] + reserve
            slip = max(_slip(path, x, ep) for x in range(max(start, j - lp.slip_lookback + 1),
                                                         j + 1))
            cj = replace(run.c0, slip_out=slip)               # deslizamiento esperado (reserva)
            got = run.peek(fav, fund, cj)
            if got[2] is not None and _fine_covers(fine, t0, path.step) and (
                    (lo <= got[2]) if s > 0 else (h >= got[2])):
                fine_bars += 1                                # ambigua: se resuelve con 1 min
                hit = _sub_bars(run, fine, path, ep, fill_t, t0, path.step, cj, reserve)
                if hit:
                    reason, ex, ex_t = hit
                    jx = j
                    break
                continue
            if (lo <= run.stop) if s > 0 else (h >= run.stop):   # SL vigente AL ABRIR la vela
                reason, ex, jx = ("SLD" if run.level else "SL"), _stop_exit(
                    path, s, j, run.stop, k), j
                break
            run.apply(got, end, cj)
    end_i = jx if jx is not None else last_ok
    hi, lo = float(path.h[k:end_i + 1].max()), float(path.l[k:end_i + 1].min())
    mfe = max(0.0, ((hi if s > 0 else lo) - fill) * s) / risk
    mae = max(0.0, (fill - (lo if s > 0 else hi)) * s) / risk
    info = {"qty": qty, "level": run.level, "nominal_usd": nominal(run.level, lp),
            "max_float_usd": None if run.max_float == -math.inf else run.max_float,
            "stop": run.stop, "initial_sl": idea.sl, "stop_history": run.hist,
            "incident": incident, "levels": [h_["nominal"] for h_ in run.hist],
            "last_bar_t": int(path.t[end_i]) + path.step, "fine_resolved_bars": fine_bars}
    if reason:
        exit_t = ex_t if ex_t is not None else int(path.t[jx]) + path.step
        fund, assumed = _funding(path, s, fill_t, exit_t, ep)
        fee_out = ep.costs.taker_fee * ex / fill
        info |= {"state": "cerrada_sl_dinamico" if run.level else "cerrada_sl_inicial",
                 "protected_est_usd": (net_usd(s, qty, fill, run.stop, fund, run.c_stop)
                                       if run.level else None), "elapsed_ms": exit_t - fill_t}
        return _with_r(Outcome(idea, "CERRADA", reason, fill_t, fill, exit_t, ex, fee_in, fee_out,
                               slip_in + _slip(path, jx, ep), fund, assumed,
                               s * (ex - fill) / fill, None, mfe, mae, ladder=info))
    mark = float(path.c[end_i])
    fund, assumed = _funding(path, s, fill_t, int(path.t[end_i]) + path.step, ep)
    info |= {"state": "incidencia" if incident else "protegida" if run.level else "inicial",
             "float_usd": net_usd(s, qty, fill, mark, fund, run.c0),
             "elapsed_ms": int(path.t[end_i]) + path.step - fill_t}
    return _with_r(Outcome(idea, "ABIERTA", "", fill_t, fill, None, None, fee_in, 0.0, slip_in,
                           fund, assumed, s * (mark - fill) / fill, None, mfe, mae, mark,
                           ladder=info))
