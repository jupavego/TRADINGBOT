"""Estadística de la puerta de validación (T49). Pura, vectorizada y reproducible con semilla.

Reutiliza `backtest/edge.py` (p de permutación, Holm) y `copytrading/stats.deflated`.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

import numpy as np

from eim.backtest.edge import perm_pvalue
from eim.copytrading.stats import deflated

CHUNK = 1000          # réplicas por bloque (acota la memoria)


def rng_for(seed: int, label: str) -> np.random.Generator:
    """Generador determinista por intento: misma semilla + misma versión = mismo resultado."""
    h = int(hashlib.sha256(label.encode()).hexdigest()[:8], 16)
    return np.random.default_rng([seed, h])


def day_block_ci(r: np.ndarray, t: np.ndarray, reps: int, level: float,
                 rng: np.random.Generator, day_ms: int = 86_400_000) -> tuple[float, float]:
    """IC del R medio por bootstrap de bloques de día (se remuestrean días completos)."""
    if len(r) < 2:
        return math.nan, math.nan
    days, inv = np.unique(np.asarray(t) // day_ms, return_inverse=True)
    k = len(days)
    sums = np.bincount(inv, weights=r, minlength=k)
    cnts = np.bincount(inv, minlength=k).astype(float)
    out = []
    for a in range(0, reps, CHUNK):
        idx = rng.integers(0, k, size=(min(CHUNK, reps - a), k))
        out.append(sums[idx].sum(axis=1) / cnts[idx].sum(axis=1))
    means = np.concatenate(out)
    q = (1 - level) / 2
    return float(np.quantile(means, q)), float(np.quantile(means, 1 - q))


def random_side_pvalue(r: np.ndarray, r_flip: np.ndarray, reps: int,
                       rng: np.random.Generator) -> float | None:
    """p unilateral de «R medio > lado al azar»: en cada réplica cada operación conserva su
    lado o toma el contrario con p = ½ (mismas fechas, distancias y costos; como C2 de T27)."""
    if len(r) == 0:
        return None
    null = []
    for a in range(0, reps, CHUNK):
        pick = rng.random((min(CHUNK, reps - a), len(r))) < 0.5
        null.append(np.where(pick, r_flip, r).mean(axis=1))
    return perm_pvalue(float(r.mean()), np.concatenate(null))


def compounded_dd(r: np.ndarray, risk: float) -> tuple[float, float]:
    """(DD máximo, retorno total) de la curva capital × (1 + risk·R) en orden de cierre."""
    if len(r) == 0:
        return 0.0, 0.0
    eq = np.concatenate([[1.0], np.cumprod(np.maximum(1 + risk * r, 0.0))])
    dd = 1 - eq / np.maximum.accumulate(eq)          # el pico parte de 1: nunca es 0
    return float(dd.max()), float(eq[-1] - 1)


def window_means(r: np.ndarray, t: np.ndarray, days: int, min_trades: int,
                 day_ms: int = 86_400_000) -> list[tuple[int, int, float]]:
    """Ventanas disjuntas de `days` días ancladas en la primera decisión: (inicio, n, R medio)
    de las que tienen ≥ `min_trades` operaciones."""
    if len(r) == 0:
        return []
    t = np.asarray(t)
    t0, span = int(t.min()), days * day_ms
    w = (t - t0) // span
    out = []
    for k in np.unique(w):
        m = w == k
        if int(m.sum()) >= min_trades:
            out.append((t0 + int(k) * span, int(m.sum()), float(r[m].mean())))
    return out


def profit_factor(r: np.ndarray) -> float | None:
    neg = float(-r[r < 0].sum())
    return float(r[r > 0].sum()) / neg if neg > 0 else None


def dsr(r: Sequence[float], attempts: int) -> float | None:
    """Sharpe deflactado por número de intentos (probabilidad de que supere al máximo nulo)."""
    got = deflated(list(r), max(attempts, 1))
    return None if got is None else float(got[0])


def buy_hold(prices: tuple[np.ndarray, np.ndarray] | None, t0: int, t1: int) -> float | None:
    """Retorno de comprar y mantener entre el primer precio con t ≥ t0 y el último con t ≤ t1
    (`prices` = (tiempos, cierres) ordenados)."""
    if prices is None or not len(prices[0]) or t1 <= t0:
        return None
    ts, cs = prices
    a, b = int(np.searchsorted(ts, t0)), int(np.searchsorted(ts, t1, "right")) - 1
    if a >= len(ts) or b <= a:
        return None
    return float(cs[b] / cs[a] - 1)
