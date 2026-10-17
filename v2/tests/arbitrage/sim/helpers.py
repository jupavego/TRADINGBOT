"""Histórico sintético para los tests del simulador de arbitraje (sin red)."""

from __future__ import annotations

import numpy as np

from eim.arbitrage.sim import ArbHistory, AssetHistory, Bars, DepthProfile, Quarterly
from eim.core import CostModel

H = 3_600_000
T0 = 1_700_000_000_000 - 1_700_000_000_000 % (8 * H)  # alineado a las liquidaciones (8 h)
FREE = CostModel(spot_fees={0: (0.0, 0.0)}, usdm_fees={0: (0.0, 0.0)},
                 usdcm_fees={0: (0.0, 0.0)})


def times(n: int, start: int = T0) -> np.ndarray:
    return start + np.arange(n, dtype=np.int64) * H


def flat(n: int, price: float | np.ndarray, start: int = T0, vq: float = 1e9) -> Bars:
    p = np.full(n, price, dtype=float) if np.isscalar(price) else np.asarray(price, float)
    return Bars.flat(times(n, start), p, source="test", vq=vq)


def funding(rate: float, n_hours: int, start: int = T0) -> tuple[tuple[int, float], ...]:
    return tuple((int(t), rate) for t in range(start, start + n_hours * H, 8 * H))


def profile(key: str, levels: tuple[tuple[float, float], ...] = ((0.5, 1e12),),
            t: int = T0) -> DepthProfile:
    """Perfil simétrico: (pb desde el medio, USD) por nivel."""
    return DepthProfile(key=key, t=t, bids=levels, asks=levels, source="test")


def carry_history(rate: float = 0.0001, n: int = 24 * 60, price: float = 50_000.0,
                  levels: tuple[tuple[float, float], ...] = ((0.5, 1e12),),
                  spot: Bars | None = None, perp: Bars | None = None) -> ArbHistory:
    """BTC con spot y perpetuo a precio constante y funding constante cada 8 h."""
    keys = ("spot:BTCUSDT", "usdm:BTCUSDT")
    return ArbHistory(
        assets={"BTC": AssetHistory(asset="BTC", spot=spot or flat(n, price),
                                    perp=perp or flat(n, price), funding=funding(rate, n),
                                    returns_15m=np.zeros(100))},
        depth=tuple(profile(k, levels) for k in keys))


def quarterly(symbol: str, delivery_t: int, price: float, settle: float | None,
              n_before: int) -> Quarterly:
    return Quarterly(symbol=symbol, delivery_t=delivery_t,
                     bars=flat(n_before, price, start=delivery_t - n_before * H),
                     settle=settle, settle_source="test")
