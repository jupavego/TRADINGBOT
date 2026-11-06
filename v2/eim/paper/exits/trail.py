"""Motor de arrastre genérico de T132: el bucle de velas que comparten M2, M3, M5, M6 y M7.

La regla de cada política solo decide **dónde querría estar el stop**; este motor se encarga de
todo lo que no se puede negociar, con la misma mecánica conservadora que `ladder.py` para que el
banco compare salidas y no artefactos:

- **Entrada idéntica** a la de la escalera y la sombra: se reutiliza `ladder._entry`, así que el
  llenado, su comisión y su deslizamiento son los mismos. Si cambiaran, el A/B mediría la entrada.
- **Trinquete:** el stop nunca se afloja. Un candidato peor que el vigente se ignora.
- **Piso de ruido:** ningún stop a menos de `n·σ` del precio de referencia (§4.2). Sin σ (`nan`) el
  piso no se aplica: la falta de datos **no aprieta**.
- **Sin anticipación:** en cada vela manda primero el stop vigente AL ABRIRLA (un hueco más allá se
  ejecuta a la apertura); el avance de esa vela solo puede mover el stop desde la vela SIGUIENTE.
  Las velas **ambiguas** —las que podrían mover el stop y volver a tocarlo— se resuelven con las
  velas de 1 min en su orden real, con la misma regla dentro de cada minuto; sin velas finas se
  queda la regla conservadora.
- **Redondeo al tick** en contra del operador, como en la escalera.
- **Barrera de tiempo** (M6) y **reversión del marco mayor** (M7) como cierres opcionales, siempre
  a la apertura de su vela.
- Datos no finitos = incidencia técnica: la posición queda ABIERTA marcada, sin cierre inventado.
- **Suelo del diario** (T135, `ladder_floor.py`, las mismas funciones que la escalera): lo que el
  diario T110 guardó de la operación manda si protege más, y si no deja reconstruirla la operación
  queda «inconsistente», abierta y sin cierre inventado. Sin `guard` no cambia nada: el banco
  corre sin él.

Puro: sin red, sin disco y sin estado global.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Protocol

import numpy as np

from eim.paper.engine import Outcome, Path, _funding, _slip, _stop_exit, _with_r
from eim.paper.excursion import Extremes
from eim.paper.exits.trail_limits import (  # noqa: F401  (reexportadas: candidatas, banco, tests)
    EPS,
    NO_LIMITS,
    TrailLimits,
    can_move,
    closes_by_htf,
    closes_by_time,
    floor_ok,
    round_against,
)
from eim.paper.ideas import Idea
from eim.paper.ladder import _entry, _fine_covers
from eim.paper.ladder_floor import Floor, Guard, adopt, arm, early, finish, settle_close
from eim.paper.params import ExecParams, SymbolSpec

MOVED, INITIAL = "SLD", "SL"
TIME, HTF = "TIEMPO", "HTF"


@dataclass
class TrailState:
    """Lo que la regla puede mirar: todo pasado o del instante, nunca futuro."""

    side: int
    fill: float
    risk: float                  # |llenado − SL inicial| en precio
    stop: float                  # stop vigente
    extreme: float               # extremo favorable alcanzado, desde el llenado
    bars: int = 0                # velas completas con la posición viva
    phase: str = "riesgo_inicial"
    moved: bool = False
    hist: list[dict] = field(default_factory=list)
    # Suelo del diario (T135): lo que `ladder_floor` lee y escribe, con los mismos nombres
    qty: float = 0.0
    level: int = 0               # veces que se movió el stop (el «escalón» del diario)
    source: str = "inicial"
    max_float: float = -math.inf
    first: float = 0.0
    step_usd: float = 0.0
    floor: Floor | None = None
    floor_due: bool = False
    recovered: dict | None = None
    superseded: dict | None = None

    @property
    def s(self) -> int:
        return self.side

    @property
    def advance_r(self) -> float:
        """Avance del extremo favorable en R (bruto, el que miran las fases)."""
        return self.advance_of(self.extreme)

    def advance_of(self, extreme: float) -> float:
        """Avance en R que supondría ese extremo. No muta nada."""
        return max(0.0, (extreme - self.fill) * self.side) / self.risk

    def prospect(self, fav: float) -> float:
        """Extremo favorable incluyendo `fav`, sin aplicarlo todavía (como `ladder.peek`)."""
        return fav if (fav - self.extreme) * self.side > 0 else self.extreme


class StopRule(Protocol):
    """Regla de una política: candidato de stop en la vela `j`, o None si no propone nada.

    `extreme` es el extremo favorable **incluyendo la vela que se está mirando**, igual que el
    `fav` que recibe `ladder._Run.peek`. Se pasa como argumento en vez de leerlo del estado para
    que la regla no vaya una vela por detrás y para que nada se mute antes de saber si la vela
    cierra la posición.
    """

    id: str

    def stop_at(self, st: TrailState, j: int, extreme: float) -> float | None:
        ...

    def phase_at(self, st: TrailState, j: int, extreme: float) -> str:
        """Fase declarada en esa vela (solo informativa salvo en M5)."""
        ...


def _apply(st: TrailState, cand: float | None, ref: float, side: int, tick: float,
           sigma_abs: float | None, floor_n: float, j: int, end: int, rule_id: str) -> None:
    """Mueve el stop si puede."""
    p = can_move(st, cand, ref, side, tick, sigma_abs, floor_n)
    if p is None:
        return
    st.stop, st.moved, st.source = p, True, rule_id
    st.level += 1
    st.hist.append({"t": end, "stop": p, "bar": j, "source": rule_id, "phase": st.phase,
                    "extreme": st.extreme, "level": st.level})


def _adopt(st: TrailState, t: int) -> None:
    """Aplica el suelo guardado si ya toca. Adoptarlo cuenta como stop movido: un cierre posterior
    es «SLD», no «SL»."""
    if st.floor_due:
        adopt(st, t)
        st.moved = st.moved or bool(st.hist)


def _arm(st: TrailState, guard: Guard | None, tick: float) -> str:
    """Prepara el suelo; devuelve el motivo de estado inconsistente ("" si no hay).

    `protected_usd` se ignora: mide un neto en USDT por escalones que aquí no existen, y el nivel
    del arrastre es el número de movimientos que ya guarda `Floor.level`.
    """
    hold = arm(st, guard, tick)
    if st.floor is not None:
        st.floor = replace(st.floor, protected_usd=None)
    return hold


def _sub_bars(st: TrailState, rule: StopRule, fine: Path, path: Path, ep: ExecParams,
              t0: int, step: int, sig, floor_n: float, tick: float, j: int,
              ) -> tuple[str, float, int] | None:
    """Vela ambigua resuelta con las velas de 1 min, en su orden real."""
    a, b = int(np.searchsorted(fine.t, t0)), int(np.searchsorted(fine.t, t0 + step))
    s = st.side
    for m in range(a, b):
        o, h, lo = float(fine.o[m]), float(fine.h[m]), float(fine.l[m])
        end = int(fine.t[m]) + fine.step
        _adopt(st, int(fine.t[m]))
        if (lo <= st.stop) if s > 0 else (h >= st.stop):      # manda el stop AL ABRIR el minuto
            gap = (o <= st.stop) if s > 0 else (o >= st.stop)
            return (MOVED if st.moved else INITIAL), (o if gap else st.stop), end
        fav = h if s > 0 else lo
        prospect = st.prospect(fav)
        st.phase = rule.phase_at(st, j, prospect)
        cand = rule.stop_at(st, j, prospect)
        st.extreme = prospect
        _apply(st, cand, fav, s, tick, sig, floor_n, j, end, rule.id)
    return None


def simulate_trail(idea: Idea, path: Path, ep: ExecParams, rule: StopRule, qty: float, *,
                   spec: SymbolSpec, sigma_abs: np.ndarray | None = None,
                   limits: TrailLimits = NO_LIMITS, fine: Path | None = None,
                   htf_dir: np.ndarray | None = None, guard: Guard | None = None) -> Outcome:
    """Simula la operación con el stop que dicte `rule`. Sin TP; el tiempo solo si `limits` lo pide.

    `sigma_abs` es σ **en precio** por vela del camino (lo que produce `features`), alineado con
    `path`; `nan` significa «sin dato» y desactiva el piso en esa vela. `htf_dir` es el signo de la
    tendencia del marco mayor por vela, para M7. `guard` es lo que el diario T110 guardó de esta
    operación (solo en el libro: el banco no lo pasa).
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
    st = TrailState(s, fill, risk, idea.sl, fill, qty=qty)
    hold = _arm(st, guard, spec.tick)                  # inconsistente: no se cierra sola (T110)
    ext = Extremes(s)
    incident, fine_bars = "", 0
    reason, ex, jx, ex_t, last_ok = "", None, None, None, k
    entry_dir = int(htf_dir[k]) if htf_dir is not None and k < len(htf_dir) else 0

    if start > k and ((path.l[k] <= idea.sl) if s > 0 else (path.h[k] >= idea.sl)) and not (
            hold := hold or early(st, int(path.t[k]) + path.step)):
        reason, ex, jx = INITIAL, idea.sl, k           # límite llenada y SL en la misma vela
    else:
        for j in range(start, len(path.t)):
            o, h, lo, cl = float(path.o[j]), float(path.h[j]), float(path.l[j]), float(path.c[j])
            if not all(math.isfinite(x) for x in (o, h, lo, cl)):
                incident = f"vela sin datos válidos en t={int(path.t[j])}"
                break
            last_ok, t0 = j, int(path.t[j])
            end = t0 + path.step
            _adopt(st, t0)
            sig = (float(sigma_abs[j]) if sigma_abs is not None and j < len(sigma_abs)
                   and math.isfinite(sigma_abs[j]) else None)
            by_time = closes_by_time(st, limits, j, start)
            if (by_time or closes_by_htf(limits, htf_dir, j, entry_dir)) and not (
                    hold := hold or early(st, t0)):
                reason, ex, jx = (TIME if by_time else HTF), o, j
                break
            fav = h if s > 0 else lo
            prospect = st.prospect(fav)                 # el extremo CON esta vela, sin aplicarlo
            st.phase = rule.phase_at(st, j, prospect)
            cand = rule.stop_at(st, j, prospect)
            # La vela es ambigua solo si el stop PODRÍA moverse ahí y además ese stop nuevo cae
            # dentro del rango de la vela. Si el piso o el trinquete lo van a rechazar, no hay
            # ambigüedad que resolver y bajar al 1 min sería recorrerlo para nada.
            rounded = can_move(st, cand, prospect, s, spec.tick, sig, limits.floor_n)
            ambiguous = rounded is not None and ((lo <= rounded) if s > 0 else (h >= rounded))
            if not hold and ambiguous and _fine_covers(fine, t0, path.step):
                fine_bars += 1
                hit = _sub_bars(st, rule, fine, path, ep, t0, path.step, sig, limits.floor_n,
                                spec.tick, j)
                if hit and not (hold := early(st, hit[2], fine_end=end)):
                    reason, ex, ex_t = hit
                    jx = j
                    break
                ext.see(fav, lo if s > 0 else h)
                st.bars += 1
                continue
            if ((lo <= st.stop) if s > 0 else (h >= st.stop)) and not (  # stop vigente AL ABRIR
                    hold := hold or early(st, end)):
                reason, ex, jx = (MOVED if st.moved else INITIAL), _stop_exit(
                    path, s, j, st.stop, k), j
                break
            ext.see(fav, lo if s > 0 else h)
            st.extreme = prospect
            _apply(st, cand, fav, s, spec.tick, sig, limits.floor_n, j, end, rule.id)
            st.bars += 1

    if reason:
        reason, ex, held = settle_close(st, reason, ex, float(path.l[jx]), float(path.h[jx]))
        st.moved = st.moved or bool(st.hist)
        if held:                                       # sin cierre inventado: sigue abierta
            hold, last_ok, jx, ex_t = held, jx, None, None
    end_i = jx if jx is not None else last_ok
    if not reason:
        hold = hold or finish(st, int(path.t[end_i]) + path.step)
    mfe, mae = ext.r(fill, risk, ex if reason else None)
    info = {"qty": qty, "rule": rule.id, "stop": st.stop, "initial_sl": idea.sl,
            "stop_history": st.hist, "moved": st.moved or bool(st.hist), "phase": st.phase,
            "bars": st.bars, "incident": incident, "fine_resolved_bars": fine_bars,
            "extreme": st.extreme, "advance_r": st.advance_r, "level": st.level,
            "stop_source": st.source, "last_bar_t": int(path.t[end_i]) + path.step,
            "recovered": st.recovered, "inconsistent": hold or None,
            "floor_superseded": st.superseded}
    if reason:
        exit_t = ex_t if ex_t is not None else int(path.t[jx]) + (
            0 if reason in (TIME, HTF) else path.step)
        fund, assumed = _funding(path, s, fill_t, exit_t, ep)
        fee_out = ep.costs.taker_fee * ex / fill
        info |= {"state": "cerrada_arrastre" if st.moved else "cerrada_sl_inicial",
                 "elapsed_ms": exit_t - fill_t}
        return _with_r(Outcome(idea, "CERRADA", reason, fill_t, fill, exit_t, ex, fee_in,
                               fee_out, slip_in + _slip(path, jx, ep), fund, assumed,
                               s * (ex - fill) / fill, None, mfe, mae, ladder=info))
    mark = float(path.c[end_i])
    fund, assumed = _funding(path, s, fill_t, int(path.t[end_i]) + path.step, ep)
    info |= {"state": "inconsistente" if hold else "incidencia" if incident else "viva",
             "elapsed_ms": int(path.t[end_i]) + path.step - fill_t}
    return _with_r(Outcome(idea, "ABIERTA", "", fill_t, fill, None, None, fee_in, 0.0, slip_in,
                           fund, assumed, s * (mark - fill) / fill, None, mfe, mae, mark,
                           ladder=info))
