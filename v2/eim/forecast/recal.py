"""Recalibración de las probabilidades de escenario (T160). Puro, sin red ni disco.

Los dos intentos de la familia pre-registrada (`PLAN/notas/T160_preregistro.md` §2):

- **M1 · priors:** `p'_i ∝ p_i · frecuencia_i / media(p_i)` sobre la ventana de ajuste.
- **M2 · isotónica:** por escenario, regresión isotónica creciente (PAV) de `1[realizado = i]` sobre
  `p_i`, interpolación lineal entre nodos, recorte a [0,01; 0,98] y renormalización.

`walk_forward` aplica el ajuste sin mirar el futuro: en cada origen solo usa resultados cuyo
horizonte ya terminó, con ventana expansiva, mínimo `MIN_FIT` y reajuste cada `REFIT` orígenes.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence
from dataclasses import dataclass

IDS = ("bull", "neutral", "bear")
MIN_FIT = 500
REFIT = 250
CLIP = (0.01, 0.98)


@dataclass(frozen=True)
class Obs:
    """Pronóstico evaluado: cuándo se hizo, cuándo acabó su horizonte, qué dijo y qué pasó."""
    made_at: int
    end_t: int
    probs: dict[str, float]
    realized: str


Recal = Callable[[dict[str, float]], dict[str, float]]


def _norm(p: dict[str, float]) -> dict[str, float]:
    s = sum(p.values())
    return {i: p[i] / s for i in IDS} if s > 0 else {i: 1 / 3 for i in IDS}


def fit_priors(train: Sequence[Obs]) -> Recal:
    n = len(train)
    w = {}
    for i in IDS:
        mean_p = sum(o.probs[i] for o in train) / n
        freq = sum(o.realized == i for o in train) / n
        w[i] = freq / mean_p if mean_p > 0 else 1.0
    return lambda p: _norm({i: p[i] * w[i] for i in IDS})


def pav(x: Sequence[float], y: Sequence[float]) -> tuple[list[float], list[float]]:
    """Regresión isotónica creciente (pool adjacent violators). Devuelve nodos (x medio, y)."""
    pts = sorted(zip(x, y, strict=True))
    blocks: list[list[float]] = []          # [suma_x, suma_y, n]
    for xi, yi in pts:
        blocks.append([xi, yi, 1.0])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] >= blocks[-1][1] / blocks[-1][2]:
            sx, sy, n = blocks.pop()
            blocks[-1][0] += sx
            blocks[-1][1] += sy
            blocks[-1][2] += n
    return [b[0] / b[2] for b in blocks], [b[1] / b[2] for b in blocks]


def _interp(xs: list[float], ys: list[float], v: float) -> float:
    if v <= xs[0]:
        return ys[0]
    if v >= xs[-1]:
        return ys[-1]
    k = bisect.bisect_right(xs, v)
    x0, x1, y0, y1 = xs[k - 1], xs[k], ys[k - 1], ys[k]
    return y0 + (y1 - y0) * (v - x0) / (x1 - x0) if x1 > x0 else y1


def fit_isotonic(train: Sequence[Obs]) -> Recal:
    nodes = {i: pav([o.probs[i] for o in train], [float(o.realized == i) for o in train])
             for i in IDS}

    def apply(p: dict[str, float]) -> dict[str, float]:
        return _norm({i: min(max(_interp(*nodes[i], p[i]), CLIP[0]), CLIP[1]) for i in IDS})
    return apply


METHODS: dict[str, Callable[[Sequence[Obs]], Recal]] = {"M1_priors": fit_priors,
                                                         "M2_isotonica": fit_isotonic}


def brier(p: dict[str, float], realized: str) -> float:
    return sum((p[i] - (i == realized)) ** 2 for i in IDS)


def walk_forward(obs: Sequence[Obs], fit: Callable[[Sequence[Obs]], Recal], *,
                 min_fit: int = MIN_FIT, refit: int = REFIT) -> list[tuple[Obs, dict[str, float]]]:
    """(observación, probabilidades recalibradas) para cada origen con ajuste disponible.

    `obs` debe ir por `made_at` ascendente. En el origen `t` entran al ajuste solo los resultados
    con `end_t ≤ t`; se reajusta cada `refit` orígenes y nunca con menos de `min_fit`.
    """
    ends = sorted(range(len(obs)), key=lambda j: obs[j].end_t)
    out: list[tuple[Obs, dict[str, float]]] = []
    model: Recal | None = None
    since = refit
    for o in obs:
        if model is None or since >= refit:
            known = [obs[j] for j in ends if obs[j].end_t <= o.made_at]
            if len(known) >= min_fit:
                model, since = fit(known), 0
        if model is not None:
            out.append((o, model(o.probs)))
            since += 1
    return out
