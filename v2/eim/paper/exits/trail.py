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

Puro: sin red, sin disco y sin estado global.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from eim.paper.engine import Outcome, Path, _funding, _slip, _stop_exit, _with_r
from eim.paper.excursion import Extremes
from eim.paper.ideas import Idea
from eim.paper.ladder import _entry, _fine_covers
from eim.paper.params import ExecParams, SymbolSpec

EPS = 1e-9
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


def round_against(price: float, side: int, tick: float) -> float:
    """Redondea al tick EN CONTRA del operador: largo hacia arriba, corto hacia abajo."""
    n = math.ceil(price / tick - EPS) if side > 0 else math.floor(price / tick + EPS)
    return round(n * tick, 8)


def floor_ok(candidate: float, ref: float, side: int, sigma_abs: float | None,
             n: float) -> bool:
    """¿El candidato respeta el piso de ruido? Sin σ no hay piso (falta de datos no aprieta)."""
    if sigma_abs is None or not math.isfinite(sigma_abs) or sigma_abs <= 0 or n <= 0:
        return True
    return (ref - candidate) * side >= n * sigma_abs - EPS


def can_move(st: TrailState, cand: float | None, ref: float, side: int, tick: float,
             sigma_abs: float | None, floor_n: float) -> float | None:
    """El stop al que se movería, o None si no se mueve. No muta nada.

    El piso de ruido se mide sobre el candidato **sin redondear**: el redondeo al tick va en
    contra del operador y es un ajuste de precisión del instrumento, no una decisión de la
    política. Si decidiera el piso, una variante con `k` igual al piso quedaría muerta por un
    tick —el stop no se movería nunca— y el banco informaría de una política inerte creyendo
    que mide la suya (medido: con k=2 y piso 2σ, 0 movimientos y 55 221 velas recorridas en
    balde por idea).
    """
    if cand is None or not math.isfinite(cand):
        return None
    if not floor_ok(cand, ref, side, sigma_abs, floor_n):
        return None
    p = round_against(cand, side, tick)
    if (p - st.stop) * side <= 0:                      # trinquete: solo sube
        return None
    if (ref - p) * side < -EPS:                        # no se pone al otro lado del precio
        return None
    return p


def _apply(st: TrailState, cand: float | None, ref: float, side: int, tick: float,
           sigma_abs: float | None, floor_n: float, j: int, end: int, rule_id: str) -> None:
    """Mueve el stop si puede."""
    p = can_move(st, cand, ref, side, tick, sigma_abs, floor_n)
    if p is None:
        return
    st.stop, st.moved = p, True
    st.hist.append({"t": end, "stop": p, "bar": j, "source": rule_id, "phase": st.phase,
                    "extreme": st.extreme})


def _sub_bars(st: TrailState, rule: StopRule, fine: Path, path: Path, ep: ExecParams,
              t0: int, step: int, sig, floor_n: float, tick: float, j: int,
              ) -> tuple[str, float, int] | None:
    """Vela ambigua resuelta con las velas de 1 min, en su orden real."""
    a, b = int(np.searchsorted(fine.t, t0)), int(np.searchsorted(fine.t, t0 + step))
    s = st.side
    for m in range(a, b):
        o, h, lo = float(fine.o[m]), float(fine.h[m]), float(fine.l[m])
        end = int(fine.t[m]) + fine.step
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


@dataclass(frozen=True)
class TrailLimits:
    """Lo que el motor impone por encima de la regla."""

    floor_n: float = 0.0          # piso de ruido en σ (0 = sin piso)
    time_bars: int | None = None  # barrera vertical (M6): cierra a la apertura de esa vela
    time_min_r: float = 0.0       # ... solo si el avance no llegó a este R
    htf_flip: bool = False        # M7: cierra si `htf_dir` del marco mayor cambia de signo


NO_LIMITS = TrailLimits()         # inmutable: sirve de valor por defecto sin construirlo cada vez


def simulate_trail(idea: Idea, path: Path, ep: ExecParams, rule: StopRule, qty: float, *,
                   spec: SymbolSpec, sigma_abs: np.ndarray | None = None,
                   limits: TrailLimits = NO_LIMITS, fine: Path | None = None,
                   htf_dir: np.ndarray | None = None) -> Outcome:
    """Simula la operación con el stop que dicte `rule`. Sin TP; el tiempo solo si `limits` lo pide.

    `sigma_abs` es σ **en precio** por vela del camino (lo que produce `features`), alineado con
    `path`; `nan` significa «sin dato» y desactiva el piso en esa vela. `htf_dir` es el signo de la
    tendencia del marco mayor por vela, para M7.
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
    st = TrailState(s, fill, risk, idea.sl, fill)
    ext = Extremes(s)
    incident, fine_bars = "", 0
    reason, ex, jx, ex_t, last_ok = "", None, None, None, k
    entry_dir = int(htf_dir[k]) if htf_dir is not None and k < len(htf_dir) else 0

    if start > k and ((path.l[k] <= idea.sl) if s > 0 else (path.h[k] >= idea.sl)):
        reason, ex, jx = INITIAL, idea.sl, k           # límite llenada y SL en la misma vela
    else:
        for j in range(start, len(path.t)):
            o, h, lo, cl = float(path.o[j]), float(path.h[j]), float(path.l[j]), float(path.c[j])
            if not all(math.isfinite(x) for x in (o, h, lo, cl)):
                incident = f"vela sin datos válidos en t={int(path.t[j])}"
                break
            last_ok, t0 = j, int(path.t[j])
            end = t0 + path.step
            sig = (float(sigma_abs[j]) if sigma_abs is not None and j < len(sigma_abs)
                   and math.isfinite(sigma_abs[j]) else None)
            if _closes_by_time(st, limits, j, start) or _closes_by_htf(limits, htf_dir, j,
                                                                      entry_dir):
                reason, ex, jx = (TIME if _closes_by_time(st, limits, j, start) else HTF), o, j
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
            if ambiguous and _fine_covers(fine, t0, path.step):
                fine_bars += 1
                hit = _sub_bars(st, rule, fine, path, ep, t0, path.step, sig, limits.floor_n,
                                spec.tick, j)
                if hit:
                    reason, ex, ex_t = hit
                    jx = j
                    break
                ext.see(fav, lo if s > 0 else h)
                st.bars += 1
                continue
            if (lo <= st.stop) if s > 0 else (h >= st.stop):     # stop vigente AL ABRIR
                reason, ex, jx = (MOVED if st.moved else INITIAL), _stop_exit(
                    path, s, j, st.stop, k), j
                break
            ext.see(fav, lo if s > 0 else h)
            st.extreme = prospect
            _apply(st, cand, fav, s, spec.tick, sig, limits.floor_n, j, end, rule.id)
            st.bars += 1

    end_i = jx if jx is not None else last_ok
    mfe, mae = ext.r(fill, risk, ex if reason else None)
    info = {"qty": qty, "rule": rule.id, "stop": st.stop, "initial_sl": idea.sl,
            "stop_history": st.hist, "moved": st.moved, "phase": st.phase,
            "bars": st.bars, "incident": incident, "fine_resolved_bars": fine_bars,
            "extreme": st.extreme, "advance_r": st.advance_r,
            "last_bar_t": int(path.t[end_i]) + path.step}
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
    info |= {"state": "incidencia" if incident else "viva",
             "elapsed_ms": int(path.t[end_i]) + path.step - fill_t}
    return _with_r(Outcome(idea, "ABIERTA", "", fill_t, fill, None, None, fee_in, 0.0, slip_in,
                           fund, assumed, s * (mark - fill) / fill, None, mfe, mae, mark,
                           ladder=info))


def _closes_by_time(st: TrailState, limits: TrailLimits, j: int, start: int) -> bool:
    """Barrera vertical (M6): tras `time_bars` velas se cierra, salvo que el avance llegara a
    `time_min_r`.

    `time_min_r = 0` significa **sin excepción**: la barrera cierra siempre a las `time_bars`
    velas. Es la barrera vertical de la triple barrera sin objetivo de beneficio. Leerlo como
    «cierra si el avance es menor que 0» dejaría el valor pre-registrado 0 inerte, porque el
    avance nunca es negativo (`advance_of` lo acota en 0): tres variantes de M6 medirían «no
    cerrar nunca» en vez de lo que declara la rejilla.
    """
    if limits.time_bars is None:
        return False
    if j - start < limits.time_bars:
        return False
    return limits.time_min_r <= 0 or st.advance_r < limits.time_min_r - EPS


def _closes_by_htf(limits: TrailLimits, htf_dir: np.ndarray | None, j: int,
                   entry_dir: int) -> bool:
    """Reversión del marco mayor (M7): el signo de `htf_dir` cambia respecto al de la entrada."""
    if not limits.htf_flip or htf_dir is None or entry_dir == 0 or j >= len(htf_dir):
        return False
    now = int(htf_dir[j])
    return now != 0 and now != entry_dir
