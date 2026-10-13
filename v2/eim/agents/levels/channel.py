"""Canal por pivotes (Theil–Sen) y detección de rango lateral. Funciones puras."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from eim.agents.levels.params import LevelsParams
from eim.agents.levels.pivots import Pivot


@dataclass(frozen=True)
class Channel:
    kind: str            # "channel" | "range"
    slope: float         # precio por vela (0 si rango)
    up_b: float          # techo: p = slope*i + up_b
    lo_b: float
    start_i: int
    r2: float
    touches: int
    state: str           # "INSIDE" | "BROKEN_UP" | "BROKEN_DOWN"

    def upper(self, i: float) -> float:
        return self.slope * i + self.up_b

    def lower(self, i: float) -> float:
        return self.slope * i + self.lo_b


def _theil_sen(x: np.ndarray, y: np.ndarray) -> list[float]:
    return [(y[j] - y[i]) / (x[j] - x[i])
            for i in range(len(x)) for j in range(i + 1, len(x)) if x[j] != x[i]]


def _r2(x: np.ndarray, y: np.ndarray, slope: float, b: float) -> float:
    ss_tot = float(((y - y.mean()) ** 2).sum())
    if ss_tot <= 0:
        return 1.0
    return max(0.0, 1.0 - float(((y - (slope * x + b)) ** 2).sum()) / ss_tot)


def fit_channel(pivots: list[Pivot], close: np.ndarray, a: float,
                p: LevelsParams) -> Channel | None:
    """Ajusta techo/piso con pendiente común robusta; `range` si la deriva es insignificante."""
    n = len(close)
    win = [x for x in pivots if x.i >= n - p.channel_lookback]
    hi = [x for x in win if x.kind == "high"]
    lo = [x for x in win if x.kind == "low"]
    if len(hi) < p.channel_min_pivots or len(lo) < p.channel_min_pivots:
        return None
    hx, hy = np.array([x.i for x in hi], float), np.array([x.price for x in hi])
    lx, ly = np.array([x.i for x in lo], float), np.array([x.price for x in lo])
    slopes = _theil_sen(hx, hy) + _theil_sen(lx, ly)
    if not slopes:
        return None
    slope = float(np.median(slopes))
    up_b = float(np.median(hy - slope * hx))
    lo_b = float(np.median(ly - slope * lx))
    start = int(min(hx.min(), lx.min()))
    width = up_b - lo_b
    if width < p.min_channel_width_atr * a:
        return None
    kind = "channel"
    if abs(slope) * (n - 1 - start) / width < p.range_drift_ratio:
        kind, slope = "range", 0.0
        up_b, lo_b = float(np.median(hy)), float(np.median(ly))
        if up_b - lo_b < p.min_channel_width_atr * a:
            return None
    tol = p.channel_touch_atr * a
    touches = int((abs(hy - (slope * hx + up_b)) <= tol).sum()
                  + (abs(ly - (slope * lx + lo_b)) <= tol).sum())
    if touches < 2 * p.channel_min_pivots - 1:
        return None
    r2 = (_r2(hx, hy, slope, up_b) + _r2(lx, ly, slope, lo_b)) / 2
    k = p.break_bars
    idx = np.arange(n - k, n, dtype=float)
    cl, m = close[-k:], p.break_margin_atr * a
    state = "INSIDE"
    if (cl > slope * idx + up_b + m).all():
        state = "BROKEN_UP"
    elif (cl < slope * idx + lo_b - m).all():
        state = "BROKEN_DOWN"
    return Channel(kind, slope, up_b, lo_b, start, r2, touches, state)
