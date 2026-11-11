"""Puntuación de los pronósticos de varianza y calibración conformal adaptativa (T162).

- QLIKE (Patton 2011): L = RV/ĥ − ln(RV/ĥ) − 1; robusta al ruido del objetivo, menor es mejor.
- CRPS cerrado de la predictiva normal N(0, ĥ) del retorno diario, y PIT = Φ(r/√ĥ).
- ACI (Gibbs y Candès 2021): la banda |r| ≤ q·√ĥ usa el cuantil 1 − α_t de los |r|/√ĥ recientes
  y α se corrige con cada fallo, así que la cobertura a largo plazo converge a la nominal aunque
  el régimen cambie.

Puro: numpy y `statistics`.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

_N = NormalDist()
_SQRT_PI = math.sqrt(math.pi)


def qlike(rv: np.ndarray, h: np.ndarray) -> np.ndarray:
    x = np.asarray(rv, float) / np.asarray(h, float)
    return x - np.log(x) - 1.0


def crps_normal(r: np.ndarray, h: np.ndarray) -> np.ndarray:
    """CRPS de N(0, h) frente al retorno observado (Gneiting y Raftery 2007)."""
    s = np.sqrt(np.asarray(h, float))
    z = np.asarray(r, float) / s
    pdf = np.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    cdf = 0.5 * (1 + _erf(z / math.sqrt(2)))
    return s * (z * (2 * cdf - 1) + 2 * pdf - 1 / _SQRT_PI)


def pit(r: np.ndarray, h: np.ndarray) -> np.ndarray:
    z = np.asarray(r, float) / np.sqrt(np.asarray(h, float))
    return 0.5 * (1 + _erf(z / math.sqrt(2)))


def _erf(x: np.ndarray) -> np.ndarray:
    return np.vectorize(math.erf)(x)


def pit_deciles(u: np.ndarray) -> list[float]:
    """Fracción de PIT en cada decil (0,1 cada uno si la predictiva está calibrada)."""
    u = np.asarray(u, float)
    u = u[np.isfinite(u)]
    if not len(u):
        return [math.nan] * 10
    hist, _ = np.histogram(u, bins=10, range=(0.0, 1.0))
    return (hist / len(u)).tolist()


def band_hits(r: np.ndarray, h: np.ndarray, level: float = 0.80) -> np.ndarray:
    """Acierto de la banda normal fija |r| ≤ z·√ĥ (sin ACI)."""
    z = _N.inv_cdf(0.5 + level / 2)
    return np.abs(np.asarray(r, float)) <= z * np.sqrt(np.asarray(h, float))


def aci_hits(r: np.ndarray, h: np.ndarray, level: float = 0.80, gamma: float = 0.005,
             window: int = 250) -> np.ndarray:
    """Acierto de la banda con ACI. Mientras no hay `window` puntuaciones previas, nan.

    Puntuación s_t = |r_t|/√ĥ_t; banda del día t = cuantil 1 − α_t de las `window` anteriores;
    α_{t+1} = α_t + γ·(α − fallo_t), con α = 1 − level.
    """
    r, h = np.asarray(r, float), np.asarray(h, float)
    alpha = 1.0 - level
    a_t = alpha
    scores: list[float] = []
    out = np.full(len(r), np.nan)
    for t in range(len(r)):
        if not (np.isfinite(r[t]) and np.isfinite(h[t]) and h[t] > 0):
            continue
        s = abs(r[t]) / math.sqrt(h[t])
        if len(scores) >= window:
            q_level = min(max(1.0 - a_t, 0.0), 1.0)
            q = float(np.quantile(scores[-window:], q_level)) if q_level < 1 else math.inf
            miss = s > q
            out[t] = 0.0 if miss else 1.0
            a_t = a_t + gamma * (alpha - float(miss))
        scores.append(s)
    return out


def worst_window(hits: np.ndarray, nominal: float, days: int = 90) -> float | None:
    """Cobertura de la ventana móvil de `days` días que más se aleja de la nominal."""
    x = np.asarray(hits, float)
    x = x[np.isfinite(x)]
    if len(x) < days:
        return None
    roll = np.convolve(x, np.ones(days) / days, mode="valid")
    return float(roll[np.argmax(np.abs(roll - nominal))])
