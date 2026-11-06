"""Lo que el motor de arrastre impone por encima de la regla (T132), separado de su bucle.

Redondeo al tick en contra del operador, piso de ruido, trinquete y las dos barreras opcionales
(tiempo para M6, reversión del marco mayor para M7). Funciones puras: `trail.py` las reexporta.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from eim.paper.exits.trail import TrailState

EPS = 1e-9


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


@dataclass(frozen=True)
class TrailLimits:
    """Lo que el motor impone por encima de la regla."""

    floor_n: float = 0.0          # piso de ruido en σ (0 = sin piso)
    time_bars: int | None = None  # barrera vertical (M6): cierra a la apertura de esa vela
    time_min_r: float = 0.0       # ... solo si el avance no llegó a este R
    htf_flip: bool = False        # M7: cierra si `htf_dir` del marco mayor cambia de signo


NO_LIMITS = TrailLimits()         # inmutable: sirve de valor por defecto sin construirlo cada vez


def closes_by_time(st: TrailState, limits: TrailLimits, j: int, start: int) -> bool:
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


def closes_by_htf(limits: TrailLimits, htf_dir: np.ndarray | None, j: int,
                  entry_dir: int) -> bool:
    """Reversión del marco mayor (M7): el signo de `htf_dir` cambia respecto al de la entrada."""
    if not limits.htf_flip or htf_dir is None or entry_dir == 0 or j >= len(htf_dir):
        return False
    now = int(htf_dir[j])
    return now != 0 and now != entry_dir
