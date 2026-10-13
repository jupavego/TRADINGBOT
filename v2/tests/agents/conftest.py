"""Fixtures compartidas de agentes: snapshot desde el CSV de ETHUSDT 1h (sin red)."""
from __future__ import annotations

import pytest

from eim.core import Candle, MarketSnapshot
from tests.legacy import _runner as r


def make_snapshot(n: int | None = None) -> MarketSnapshot:
    df = r.load_ohlcv()
    df = df if n is None else df.iloc[:n]
    candles = [
        Candle(t=int(ts.timestamp() * 1000), o=o, h=h, l=lo, c=c, v=v)
        for ts, o, h, lo, c, v in df.itertuples(index=False)
    ]
    return MarketSnapshot(
        symbol="ETHUSDT", timeframe="1h", candles=candles, asof=candles[-1].t + 3_600_000,
        sources={"candles": "fixture ethusdt_1h_1000.csv"},
        coverage={"candles": (candles[0].t, candles[-1].t)},
    )


@pytest.fixture(scope="session")
def snapshot() -> MarketSnapshot:
    return make_snapshot()
