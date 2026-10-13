"""Relleno incremental del almacén desde un proveedor."""

from __future__ import annotations

import time

from eim.data.providers.base import Provider
from eim.data.store import Store
from eim.data.timeframes import tf_ms


def sync_candles(
    store: Store,
    provider: Provider,
    symbol: str,
    timeframe: str,
    start: int,
    end: int | None = None,
) -> dict[str, int]:
    """Descarga lo que falta en [start, end): historia previa, huecos internos y cola nueva.

    Devuelve {"fetched": velas descargadas, "total": filas en el almacén, "gaps": huecos restantes}.
    """
    step = tf_ms(timeframe)
    end = end if end is not None else int(time.time() * 1000)
    start -= start % step
    bounds = store.bounds(symbol, timeframe)
    ranges: list[tuple[int, int]] = []
    if bounds is None:
        ranges.append((start, end))
    else:
        if bounds[0] > start:
            ranges.append((start, bounds[0]))
        ranges += [(g0, g1 + step) for g0, g1 in store.find_gaps(symbol, timeframe)]
        ranges.append((bounds[1] + step, end))
    fetched = 0
    for a, b in ranges:
        if a >= b:
            continue
        candles = provider.klines(symbol, timeframe, a, b)
        if candles:
            fetched += len(candles)
            store.upsert_candles(symbol, timeframe, candles, provider.name)
    total = len(store.read_candles(symbol, timeframe))
    return {"fetched": fetched, "total": total, "gaps": len(store.find_gaps(symbol, timeframe))}


def sync_derivatives(
    store: Store, provider: Provider, symbol: str, timeframe: str, start: int, end: int
) -> dict[str, int]:
    """Funding (completo) y open interest (solo lo que Binance retenga) en [start, end)."""
    f = store.read_series("funding", symbol)
    rates = provider.funding_rates(symbol, f[-1][0] + 1 if f else start, end)
    if rates:
        store.upsert_series("funding", symbol, "-", rates, provider.name)
    o = store.read_series("open_interest", symbol, timeframe)
    oi = provider.open_interest(symbol, timeframe, o[-1][0] + tf_ms(timeframe) if o else start, end)
    if oi:
        store.upsert_series("open_interest", symbol, timeframe, oi, provider.name)
    out = {"funding": len(rates), "open_interest": len(oi)}
    for kind in ("long_short_ratio", "basis"):  # opcionales: el proveedor puede no tenerlos
        fetch = getattr(provider, kind, None)
        if fetch is None:
            continue
        old = store.read_series(kind, symbol, timeframe)
        rows = fetch(symbol, timeframe, old[-1][0] + tf_ms(timeframe) if old else start, end)
        if rows:
            store.upsert_series(kind, symbol, timeframe, rows, provider.name)
        out[kind] = len(rows)
    return out
