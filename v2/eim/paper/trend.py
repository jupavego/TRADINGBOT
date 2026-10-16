"""Tendencia del marco mayor (T48b): dirección de EMA rápida frente a EMA lenta en la última vela
del marco mayor CERRADA en el instante pedido (sin anticipación)."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence

import numpy as np

from eim.core import Candle
from eim.indicators._core import ema


class HtfTrend:
    def __init__(self, candles: Sequence[Candle], bar_ms: int, fast: int, slow: int) -> None:
        c = np.array([x.c for x in candles], dtype=float)
        self._close_t = [x.t + bar_ms for x in candles]
        self._dir = np.sign(ema(c, fast) - ema(c, slow)) if len(c) else np.array([])
        self._warm = slow                 # sin dirección hasta tener `slow` velas

    def at(self, t: int) -> int:
        """+1 alcista, −1 bajista, 0 sin dato, según la última vela cerrada en `t` o antes."""
        k = bisect_right(self._close_t, t) - 1
        if k < self._warm:
            return 0
        return int(self._dir[k])
