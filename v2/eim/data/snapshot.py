"""Construcción de `MarketSnapshot` desde el almacén (sin red)."""

from __future__ import annotations

import time

from eim.core import MarketSnapshot
from eim.data.micro import read_micro
from eim.data.store import Store
from eim.data.timeframes import tf_ms


def build_snapshot(
    store: Store, symbol: str, timeframe: str, n: int, asof: int | None = None
) -> MarketSnapshot:
    """Últimas `n` velas cerradas a `asof` (ms, por defecto ahora) + funding/OI si existen.

    `sources` y `coverage` reflejan lo realmente almacenado: si hay menos de `n` velas,
    la cobertura lo muestra. Funding y OI se limitan a la ventana de las velas.
    """
    step = tf_ms(timeframe)
    asof = asof if asof is not None else int(time.time() * 1000)
    candles = store.read_candles(symbol, timeframe, end=asof - step + 1, last=n)
    sources: dict[str, str] = {}
    coverage: dict[str, tuple[int, int]] = {}
    funding = oi = ls = basis = None
    micro = book = None
    if candles:
        lo, hi = candles[0].t, candles[-1].t
        sources["candles"] = store.source("candles", symbol, timeframe) or "desconocida"
        coverage["candles"] = (lo, hi)
        end = min(asof, hi + step)
        funding = store.read_series("funding", symbol, start=lo, end=end) or None
        oi = store.read_series("open_interest", symbol, timeframe, start=lo, end=end) or None
        ls = store.read_series("long_short_ratio", symbol, timeframe, start=lo, end=end) or None
        basis = store.read_series("basis", symbol, timeframe, start=lo, end=end) or None
        for name, series, tf in (("funding", funding, "-"), ("open_interest", oi, timeframe),
                                 ("long_short_ratio", ls, timeframe), ("basis", basis, timeframe)):
            if series:
                sources[name] = store.source(name, symbol, tf) or "desconocida"
                coverage[name] = (series[0][0], series[-1][0])
        bars, book = read_micro(store.root, symbol, lo, step, (hi - lo) // step + 1)
        if bars:
            micro = bars
            sources["micro"] = "binance_ws"
            coverage["micro"] = (bars[0].t, bars[-1].t)
        if book is not None:
            sources["orderbook"] = book.source
    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        funding=funding,
        open_interest=oi,
        long_short_ratio=ls,
        basis=basis,
        micro=micro,
        orderbook=book,
        asof=asof,
        sources=sources,
        coverage=coverage,
    )
