"""Relleno histórico de `bot_signals` (T58): posturas de cada cierre de vela en una ventana pasada.

Sirve para dejar, con datos reales, ≥ 6 meses de posturas de cada adaptador direccional antes de que
T59 los puntúe. Cada señal sale de un snapshot que contiene SOLO las velas hasta su cierre (la
misma `closed_candles_only` que el ciclo en vivo), y se guarda con `created_ms` = ahora: la tabla
registra que es un relleno, no una opinión de aquel momento.

    python -m eim.bots.backfill --symbol BTCUSDT --timeframe 1h --since 2026-04-19
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.api.reports_db import ReportStore
from eim.bots.hb_directional import HummingbotDirectionalAdapter
from eim.bots.service import FT_ENGINE_ENV, FT_PY_ENV, BotService
from eim.core import BotSignal, Candle, MarketSnapshot
from eim.data.bots.store import BotSignalStore
from eim.data.store import Store
from eim.data.timeframes import tf_ms

HISTORY_BARS = 1000   # velas previas que ve cada snapshot (como en el ciclo en vivo)


def snapshots(candles: list[Candle], symbol: str, timeframe: str, from_asof: int,
              history: int = HISTORY_BARS):
    """Un snapshot por cierre de vela con `asof` ≥ `from_asof`, con las `history` velas previas."""
    step = tf_ms(timeframe)
    for i, c in enumerate(candles):
        if c.t + step >= from_asof:
            yield MarketSnapshot(symbol=symbol, timeframe=timeframe, asof=c.t + step,
                                 candles=candles[max(0, i + 1 - history):i + 1],
                                 sources={"candles": "almacén local (relleno histórico)"})


def backfill_pure(service: BotService, candles: list[Candle], symbol: str, timeframe: str,
                  from_asof: int) -> int:
    """Modo A (y cualquier adaptador barato): una pasada por vela por el servicio normal."""
    n = 0
    for snap in snapshots(candles, symbol, timeframe, from_asof):
        n += sum(1 for s in service.produce(snap) if s.status == "ok")
    return n


def backfill_ft(store: BotSignalStore, adapter, candles: list[Candle], symbol: str,
                timeframe: str, from_asof: int, created_ms: int) -> dict[str, int]:
    """Modo B: una corrida aislada por estrategia sobre toda la ventana (ver `history`)."""
    snap = MarketSnapshot(symbol=symbol, timeframe=timeframe, candles=candles,
                          asof=candles[-1].t + tf_ms(timeframe),
                          sources={"candles": "almacén local (relleno histórico)"})
    out: dict[str, int] = {}
    for strategy in adapter.strategies:
        sigs: list[BotSignal] = adapter.history(snap, strategy, from_asof)
        out[strategy] = store.append_many(sigs, created_ms)
    return out


def _ms(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eim.bots.backfill", description=__doc__)
    p.add_argument("--data-dir", default=os.environ.get("EIM_DATA_DIR", "data"))
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--since", required=True, help="primer día (UTC, AAAA-MM-DD) con posturas")
    a = p.parse_args(argv)
    data, tf = Path(a.data_dir), a.timeframe
    candles = Store(data).read_candles(a.symbol, tf)
    from_asof = _ms(a.since)
    if not candles or candles[0].t + HISTORY_BARS * tf_ms(tf) > from_asof:
        print("el almacén no cubre la ventana pedida más las velas previas de calentamiento")
        return 2
    reports = ReportStore(data / "reports.duckdb")
    store = BotSignalStore(*reports.connection)
    now = int(time.time() * 1000)
    service = BotService([HummingbotDirectionalAdapter()], store, clock=lambda: now)
    print("hummingbot-directional:", backfill_pure(service, candles, a.symbol, tf, from_asof),
          "señales ok")
    py, engine = os.environ.get(FT_PY_ENV), os.environ.get(FT_ENGINE_ENV)
    checkout = data / "bots" / "freqtrade-strategies"
    if py and engine and checkout.exists():
        from eim.bots.ft_adapter import FreqtradeAdapter

        ft = FreqtradeAdapter(Path(py), checkout, engine)
        done = backfill_ft(store, ft, candles, a.symbol, tf, from_asof, now)
        print("freqtrade-strategies:", done)
    else:
        print("freqtrade-strategies: sin entorno aparte (EIM_BOT_FREQTRADE_*): no se rellena")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
