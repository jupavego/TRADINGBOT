"""Series sintéticas deterministas (alcista, bajista, rango) para el agente `technical`."""
from __future__ import annotations

import numpy as np

from eim.core import Candle, MarketSnapshot

HOUR = 3_600_000
T0 = 1_700_000_000_000 // (4 * HOUR) * (4 * HOUR)  # alineado a 4h para el remuestreo


def candles(kind: str, n: int = 600, seed: int = 0, step: int = HOUR,
            flow: bool = True) -> list[Candle]:
    rng = np.random.default_rng(seed)
    i = np.arange(n)
    drift = {"up": 0.002, "down": -0.002}.get(kind, 0.0)
    if kind == "range":  # Ornstein-Uhlenbeck: revierte a 100
        x = np.zeros(n)
        for k in range(1, n):
            x[k] = 0.8 * x[k - 1] + rng.normal(0, 0.004)
        c = 100 * np.exp(x)
    else:
        c = 100 * np.exp(drift * i + rng.normal(0, 0.003, n))
    o = np.r_[c[0], c[:-1]]
    h, lo = np.maximum(o, c) * 1.002, np.minimum(o, c) * 0.998
    v = 1000 + rng.random(n) * 100
    tilt = {"up": 0.1, "down": -0.1}.get(kind, 0.0)
    buy = v * (0.5 + tilt + rng.normal(0, 0.02, n))
    return [Candle(t=T0 + k * step, o=o[k], h=h[k], l=lo[k], c=c[k], v=v[k],
                   taker_buy_v=float(buy[k]) if flow else None, trades=100 if flow else None)
            for k in range(n)]


def snapshot(kind: str, n: int = 600, **kw) -> MarketSnapshot:
    cs = candles(kind, n, **kw)
    return MarketSnapshot(symbol="SYNTH", timeframe="1h", candles=cs, asof=cs[-1].t + HOUR,
                          sources={"candles": f"sintética {kind}"},
                          coverage={"candles": (cs[0].t, cs[-1].t)})
