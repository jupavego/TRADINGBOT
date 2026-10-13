"""Pivotes, ATR y zonas de soporte/resistencia (clustering 1D). Funciones puras."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from eim.agents.levels.params import LevelsParams


@dataclass(frozen=True)
class Pivot:
    i: int          # índice de vela
    price: float
    kind: str       # "high" | "low"
    volume: float


@dataclass(frozen=True)
class Zone:
    p_low: float
    p_high: float
    touches: int
    score: float
    first_i: int    # índice del primer toque
    last_i: int     # índice del último toque

    @property
    def mid(self) -> float:
        return (self.p_low + self.p_high) / 2


def atr(h: np.ndarray, lo: np.ndarray, c: np.ndarray, period: int) -> float:
    """ATR simple (media del rango verdadero) de las últimas `period` velas."""
    prev = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - lo, np.maximum(abs(h - prev), abs(lo - prev)))
    return float(tr[-period:].mean())


def find_pivots(h: np.ndarray, lo: np.ndarray, v: np.ndarray, n: int) -> list[Pivot]:
    """Fractales confirmados (n velas a cada lado); el último tramo no confirma."""
    out: list[Pivot] = []
    for i in range(n, len(h) - n):
        if int(h[i - n:i + n + 1].argmax()) == n:
            out.append(Pivot(i, float(h[i]), "high", float(v[i])))
        if int(lo[i - n:i + n + 1].argmin()) == n:
            out.append(Pivot(i, float(lo[i]), "low", float(v[i])))
    return out


def build_zones(pivots: list[Pivot], n_bars: int, a: float, med_vol: float,
                p: LevelsParams) -> list[Zone]:
    """Agrupa pivotes cercanos (altos y bajos: un nivel roto cambia de rol) en zonas."""
    tol = p.zone_cluster_atr * a
    items = sorted((x for x in pivots if x.i >= n_bars - p.zone_lookback),
                   key=lambda x: x.price)
    clusters: list[list[Pivot]] = []
    for x in items:
        cur = clusters[-1] if clusters else None
        if cur and x.price - cur[0].price <= 2 * tol \
                and x.price - sum(y.price for y in cur) / len(cur) <= tol:
            cur.append(x)
        else:
            clusters.append([x])
    zones = []
    for cl in clusters:
        if len(cl) < p.zone_min_touches:
            continue
        lo_, hi_ = min(y.price for y in cl), max(y.price for y in cl)
        pad = max(0.0, p.zone_min_thickness_atr * a - (hi_ - lo_)) / 2
        score = sum(
            math.exp(-(n_bars - 1 - y.i) / p.recency_half_life)
            * (0.75 + 0.25 * min(2.0, y.volume / med_vol if med_vol > 0 else 1.0))
            for y in cl)
        zones.append(Zone(lo_ - pad, hi_ + pad, len(cl), score,
                          min(y.i for y in cl), max(y.i for y in cl)))
    return zones


def select_zones(zones: list[Zone], close: float, p: LevelsParams) -> list[Zone]:
    """Las `max_zones_per_side` más cercanas por lado entre las de puntuación relevante.

    Ordenar por cercanía (no por puntuación pura) evita que el conjunto cambie
    bruscamente al añadir una vela; el umbral descarta zonas débiles.
    """
    if not zones:
        return []
    floor = p.zone_min_rel_score * max(z.score for z in zones)
    zones = [z for z in zones if z.score >= floor]
    above = [z for z in zones if z.mid >= close]
    below = [z for z in zones if z.mid < close]

    def top(zs: list[Zone]) -> list[Zone]:
        return sorted(zs, key=lambda z: abs(z.mid - close))[: p.max_zones_per_side]

    return sorted(top(above) + top(below), key=lambda z: z.p_low)
