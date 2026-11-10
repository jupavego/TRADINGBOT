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

HOUR_MS = 3_600_000


def _level_series(store: Store, kind: str, symbol: str, timeframe: str, lo: int, end: int,
                  sources: dict, coverage: dict) -> list | None:
    """Serie de nivel (OI, long/short, basis) del marco; si el marco no tiene y es múltiplo de 1 h,
    los puntos de 1 h que caen en su frontera (T120: el ciclo solo sincroniza 1 h y en 4 h
    `derivatives` salía siempre «sin datos»). Son niveles, no sumas: muestrear no inventa nada, y
    `sources` lo dice. Nunca se rellena hacia abajo (15 m sigue sin dato)."""
    step = tf_ms(timeframe)
    rows = store.read_series(kind, symbol, timeframe, start=lo, end=end) or None
    src_tf = timeframe
    if rows is None and step > HOUR_MS and step % HOUR_MS == 0:
        rows = [r for r in store.read_series(kind, symbol, "1h", start=lo, end=end)
                if r[0] % step == 0] or None
        src_tf = "1h"
    if rows:
        src = store.source(kind, symbol, src_tf) or "desconocida"
        sources[kind] = src if src_tf == timeframe else f"{src} (muestreo de 1h)"
        coverage[kind] = (rows[0][0], rows[-1][0])
    return rows


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
        if funding:
            sources["funding"] = store.source("funding", symbol, "-") or "desconocida"
            coverage["funding"] = (funding[0][0], funding[-1][0])
        oi, ls, basis = (_level_series(store, k, symbol, timeframe, lo, end, sources, coverage)
                         for k in ("open_interest", "long_short_ratio", "basis"))
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
