"""Construcción de `MarketSnapshot` desde el almacén (sin red)."""

from __future__ import annotations

import time

from eim.core import MarketSnapshot
from eim.data.arb_store import ArbStore, arb_sources
from eim.data.calendar import read_calendar
from eim.data.extras import read_headlines, read_liquidations
from eim.data.leader_board import BoardStore, snapshot_inputs
from eim.data.liq_flow import read_liq_flow
from eim.data.micro import read_micro
from eim.data.store import Store
from eim.data.timeframes import TF_MS, tf_ms


def build_snapshot(
    store: Store, symbol: str, timeframe: str, n: int, asof: int | None = None
) -> MarketSnapshot:
    """Últimas `n` velas cerradas a `asof` (ms, por defecto ahora) + funding/OI si existen.

    `sources` y `coverage` reflejan lo realmente almacenado: si hay menos de `n` velas,
    la cobertura lo muestra. Funding y OI se limitan a la ventana de las velas.
    `events` (T36): calendario conocido a `asof` en −24 h … +7 d; None si nunca se sincronizó.
    `arb` (T39): último escaneo de arbitraje no posterior a `asof` (≤ 10 min); None si no hay.
    `leaders`/`leader_weights` (T41): posiciones y calidad de los líderes aprobados del último
    tablero no posterior a `asof` (≤ 10 min); None si no hay tablero (vigilante apagado).
    """
    step = tf_ms(timeframe)
    asof = asof if asof is not None else int(time.time() * 1000)
    candles = store.read_candles(symbol, timeframe, end=asof - step + 1, last=n)
    sources: dict[str, str] = {}
    coverage: dict[str, tuple[int, int]] = {}
    funding = oi = ls = basis = candles_tf = None
    micro = book = liq_flow = None
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
        flow = read_liq_flow(store.root, symbol, lo, step, (hi - lo) // step + 1)
        if flow:
            liq_flow = flow
            sources["liq_flow"] = "liquidaciones en vivo binance+bybit+okx (Binance: cota inferior)"
            coverage["liq_flow"] = (flow[0].t, flow[-1].t)
        if book is not None:
            sources["orderbook"] = book.source
        candles_tf = _neighbor_candles(store, symbol, timeframe, n, asof, sources, coverage)
    events = None
    cal = read_calendar(store.root, asof)
    if cal is not None:
        events, cal_sources, cal_coverage = cal
        sources |= cal_sources
        coverage |= cal_coverage
    arb = ArbStore(store.root).at(asof)
    if arb is not None:
        arb_src, arb_cov = arb_sources(arb)
        sources |= arb_src
        coverage |= arb_cov
    liquidations = read_liquidations(store.root, symbol, asof)
    if liquidations is not None:
        sources["liquidations"] = liquidations.source
        coverage["liquidations"] = (liquidations.daily[0].t, liquidations.daily[-1].t)
    headlines = read_headlines(store.root, asof)
    if headlines:
        sources["headlines"] = "rss: " + ", ".join(sorted({n.source for n in headlines}))
        coverage["headlines"] = (headlines[-1].t, headlines[0].t)
    leaders = weights = None
    board = BoardStore(store.root).at(asof)
    if board is not None:
        leaders, weights, ld_src, ld_cov = snapshot_inputs(board)
        sources |= ld_src
        coverage |= ld_cov
    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        funding=funding,
        open_interest=oi,
        long_short_ratio=ls,
        basis=basis,
        micro=micro,
        liquidations=liquidations,
        liq_flow=liq_flow,
        headlines=headlines,
        orderbook=book,
        candles_tf=candles_tf,
        events=events,
        arb=arb,
        leaders=leaders,
        leader_weights=weights,
        asof=asof,
        sources=sources,
        coverage=coverage,
    )


def _neighbor_candles(store: Store, symbol: str, timeframe: str, n: int, asof: int,
                      sources: dict[str, str], coverage: dict[str, tuple[int, int]]):
    """Velas cerradas a `asof` de los marcos vecinos; None si no hay ninguno almacenado."""
    ladder = sorted(TF_MS, key=TF_MS.__getitem__)
    i = ladder.index(timeframe)
    out = {}
    for tf in ladder[max(0, i - 1):i] + ladder[i + 1:i + 2]:
        cs = store.read_candles(symbol, tf, end=asof - TF_MS[tf] + 1, last=n)
        if cs:
            out[tf] = cs
            sources[f"candles_{tf}"] = store.source("candles", symbol, tf) or "desconocida"
            coverage[f"candles_{tf}"] = (cs[0].t, cs[-1].t)
    return out or None
