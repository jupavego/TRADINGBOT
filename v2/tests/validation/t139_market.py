"""Mercado sintético de las pruebas de T139: paseo aleatorio, sin ventaja que encontrar."""

from __future__ import annotations

import numpy as np

from eim.core import Candle
from eim.data.timeframes import tf_ms
from eim.validation.hypotheses import rules as ru
from eim.validation.hypotheses import world as wd
from eim.validation.lineage import iso_ms

M = 60_000
T0 = iso_ms("2022-01-01T00:00:00Z")
DAYS = 130


def _candle(a: np.ndarray, flow: np.ndarray, step: int, i: int, k: int, t0: int) -> Candle:
    seg = a[i:i + k]
    return Candle(t=t0 + i * step, o=float(seg[0]), h=float(seg.max() * 1.0005),
                  l=float(seg.min() * 0.9995), c=float(seg[-1]), v=float(k),
                  taker_buy_v=float(k) * float(flow[i]), trades=k)


def make_world() -> wd.World:
    """130 días de paseo aleatorio: no hay ventaja que encontrar."""
    rng = np.random.default_rng(139)
    n = DAYS * 24 * 4
    px = 30000 * np.exp(np.cumsum(rng.normal(0, 0.0012, n)))
    flow = np.clip(rng.normal(0.5, 0.12, n), 0.05, 0.95)     # compra agresora, ruido sin más
    fifteen = [_candle(px, flow, 15 * M, i, 1, T0) for i in range(n)]
    bars = {"15m": fifteen}
    for tf, k in (("1h", 4), ("4h", 16)):
        bars[tf] = [_candle(px, flow, 15 * M, i, k, T0) for i in range(0, n - k + 1, k)]
        step = tf_ms(tf)
        bars[tf] = [c.model_copy(update={"t": T0 + j * step}) for j, c in enumerate(bars[tf])]
    funding = [(T0 + 8 * 3_600_000 * j, float(rng.normal(1e-4, 1e-4))) for j in range(DAYS * 3)]
    nm = DAYS * 1440
    mp = 30000 * np.exp(np.cumsum(rng.normal(0, 0.0003, nm)))
    r = rng.uniform(1e-4, 5e-4, nm)
    mins = ru.Minutes(T0 + np.arange(nm, dtype=np.int64) * M, mp.copy(), mp * (1 + r), mp * (1 - r),
                      mp * (1 + rng.normal(0, 1e-4, nm)), rng.lognormal(0, 1, nm))
    return wd.world_of("BTCUSDT", bars, funding, mins)


def prior_keys() -> dict:
    return {f"BTCUSDT|previa{k}@1h@v1": None for k in range(832)}
