"""Reglas de stop de T132: M2 (volatilidad), M3 (estructura) y M5 (híbrida por fases).

Cada regla solo dice **dónde querría estar el stop** en una vela; el trinquete, el piso de ruido,
el redondeo al tick, los huecos y el orden dentro de la vela los impone `trail.py`. Así la regla
cabe en unas líneas, se lee de un vistazo y no puede saltarse una salvaguarda por descuido.

- **M2 Chandelier** (§3): `extremo favorable − k·σ`, activo solo desde un avance de `a` R. Antes de
  ese avance no propone nada, así que manda el SL inicial. Es el candidato base: dos parámetros y
  arrastre proporcional al ruido.
- **M3 Estructura** (§3): último swing **confirmado** de 15 m (fractal de 3 o 5 velas) menos un
  colchón de `b·σ`. «Confirmado» es lo que hace que no haya anticipación: un swing de 5 velas no
  existe hasta que han cerrado las dos posteriores.
- **M5 Híbrida** (§4.1): una sola política por fase, **nunca el máximo de varias** (H5 de T129).
  riesgo inicial → supervivencia (no se mueve el stop hasta que el avance supera el MAE típico de
  las ganadoras) → equilibrio+ (entrada + costos + `b` R) → arrastre (M2 o M3).

El `b` del BE+ de M5 incluye el costo estimado de ida y vuelta, como en `engine.simulate`, para que
la salida quede en ganancia neta y no solo nominal.

Puro: sin red, sin disco y sin estado global.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from eim.paper.exits.trail import TrailState

INITIAL_PHASE, SURVIVAL, BREAK_EVEN, TRAIL = (
    "riesgo_inicial", "supervivencia", "equilibrio_mas", "arrastre")


def _sig(sigma_abs: np.ndarray | None, j: int) -> float | None:
    """σ en precio de la vela `j`, o None si no hay dato (nunca 0)."""
    if sigma_abs is None or j >= len(sigma_abs):
        return None
    v = float(sigma_abs[j])
    return v if math.isfinite(v) and v > 0 else None


@dataclass(frozen=True)
class Chandelier:
    """M2 — `extremo − k·σ`, desde un avance de `activate_r` R."""

    k: float
    sigma_abs: np.ndarray | None
    activate_r: float = 0.0
    id: str = "M2"

    def phase_at(self, st: TrailState, j: int, extreme: float) -> str:
        return TRAIL if st.advance_of(extreme) >= self.activate_r - 1e-12 else INITIAL_PHASE

    def stop_at(self, st: TrailState, j: int, extreme: float) -> float | None:
        if st.advance_of(extreme) < self.activate_r - 1e-12:
            return None
        s = _sig(self.sigma_abs, j)
        return None if s is None else extreme - st.side * self.k * s


@dataclass(frozen=True)
class Structure:
    """M3 — último swing confirmado de 15 m menos un colchón de `buffer_sigma`·σ.

    `swing_low` y `swing_high` son arreglos alineados con el camino: el valor en la vela `j` es el
    último swing **ya confirmado** al cerrar `j` (los calcula `features.swings`, que solo mira
    atrás). Si no hay swing válido, la regla no propone nada y manda el SL inicial.
    """

    swing_low: np.ndarray | None
    swing_high: np.ndarray | None
    sigma_abs: np.ndarray | None
    buffer_sigma: float = 0.25
    id: str = "M3"

    def phase_at(self, st: TrailState, j: int, extreme: float) -> str:
        return TRAIL

    def stop_at(self, st: TrailState, j: int, extreme: float) -> float | None:
        arr = self.swing_low if st.side > 0 else self.swing_high
        if arr is None or j >= len(arr):
            return None
        anchor = float(arr[j])
        if not math.isfinite(anchor):
            return None
        s = _sig(self.sigma_abs, j)
        pad = 0.0 if s is None else self.buffer_sigma * s
        return anchor - st.side * pad


@dataclass(frozen=True)
class Hybrid:
    """M5 — fases con UNA política cada una; el stop de una fase no compite con el de otra.

    `survival_r` es el umbral de avance que cierra la fase de supervivencia. Viene del MAE típico
    de las ganadoras calculado **sin fuga** (E5, `winners_mae.py`); si no hay muestra suficiente se
    usa el valor base que se le pase.
    """

    trail: Chandelier | Structure
    survival_r: float
    be_trigger_r: float
    be_lock_r: float
    est_cost_frac: float = 0.0
    id: str = "M5"

    @property
    def gate_r(self) -> float:
        """Avance a partir del cual el stop puede moverse: las dos fases previas se han cumplido."""
        return max(self.survival_r, self.be_trigger_r)

    def _be_stop(self, st: TrailState) -> float:
        """Entrada + costos estimados + `be_lock_r` R, como el BE+ de `engine.simulate`."""
        extra = self.est_cost_frac * st.fill / st.risk if st.risk > 0 else 0.0
        return st.fill + st.side * (self.be_lock_r + extra) * st.risk

    def phase_at(self, st: TrailState, j: int, extreme: float) -> str:
        """La fase declarada es la del stop que de verdad manda en esa vela."""
        if st.advance_of(extreme) < self.gate_r - 1e-12:
            return SURVIVAL if self.survival_r > 0 else INITIAL_PHASE
        cand = self.trail.stop_at(st, j, extreme)
        if cand is None or not math.isfinite(cand):
            return BREAK_EVEN
        return TRAIL if (cand - self._be_stop(st)) * st.side >= 0 else BREAK_EVEN

    def stop_at(self, st: TrailState, j: int, extreme: float) -> float | None:
        if st.advance_of(extreme) < self.gate_r - 1e-12:
            return None                       # supervivencia: el stop NO se mueve todavía
        be = self._be_stop(st)
        cand = self.trail.stop_at(st, j, extreme)
        if cand is None or not math.isfinite(cand):
            return be                         # sin σ ni swing, la fase es el BE+
        # Una sola política por fase (H5): manda el arrastre en cuanto propone por encima del BE+,
        # y el BE+ mientras no llegue. Nunca «el mejor de varios candidatos».
        return cand if (cand - be) * st.side >= 0 else be


@dataclass(frozen=True)
class FixedStop:
    """Regla que no mueve nada: el SL inicial manda hasta el final (base de S1, M6 y M7)."""

    id: str = "M_fijo"

    def phase_at(self, st: TrailState, j: int, extreme: float) -> str:
        return INITIAL_PHASE

    def stop_at(self, st: TrailState, j: int, extreme: float) -> float | None:
        return None
