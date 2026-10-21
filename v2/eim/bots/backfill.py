"""Relleno histórico de `bot_signals` (T58): posturas de cada cierre de vela en una ventana pasada.

Sirve para dejar, con datos reales, ≥ 6 meses de posturas de cada adaptador direccional antes de que
T59 los puntúe. Cada señal sale de un snapshot que contiene SOLO las velas hasta su cierre (la
misma `closed_candles_only` que el ciclo en vivo), y se guarda con `created_ms` = ahora: la tabla
registra que es un relleno, no una opinión de aquel momento.

    python -m eim.bots.backfill --symbol BTCUSDT --timeframe 1h --since 2026-04-19
    python -m eim.bots.backfill --symbol BTCUSDT --timeframe 5m --since 2026-04-19   # NFI (5 min)

En 1 h corren Hummingbot, Jesse, TrendRider y Freqtrade; en 5 min, solo NFI (modo B). Las velas de
5 min se agregan del almacén de 1 min (`aggregate`), nunca se piden a la API.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.api.reports_db import ReportStore
from eim.bots.hb_directional import HummingbotDirectionalAdapter
from eim.bots.jesse_examples import JesseExamplesAdapter
from eim.bots.nfi_adapter import INFO_DAYS, NFI_DIR_ENV
from eim.bots.service import FT_ENGINE_ENV, FT_PY_ENV, BotService
from eim.bots.trendrider import TrendRiderAdapter
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
                timeframe: str, from_asof: int, created_ms: int,
                candles_tf: dict[str, list[Candle]] | None = None) -> dict[str, int]:
    """Modo B: una corrida aislada por estrategia sobre toda la ventana (ver `history`)."""
    snap = MarketSnapshot(symbol=symbol, timeframe=timeframe, candles=candles,
                          asof=candles[-1].t + tf_ms(timeframe), candles_tf=candles_tf,
                          sources={"candles": "almacén local (relleno histórico)"})
    out: dict[str, int] = {}
    for strategy in adapter.strategies:
        sigs: list[BotSignal] = adapter.history(snap, strategy, from_asof)
        out[strategy] = store.append_many(sigs, created_ms)
    return out


def aggregate(store: Store, symbol: str, src: str = "1m", dst: str = "5m") -> int:
    """Agrega velas del almacén (`src`→`dst`) con DuckDB, solo grupos completos, y las guarda.

    Devuelve las velas de `dst` escritas. No descarga nada: el marco 5m es solo de almacén."""
    import duckdb

    from eim.core import Candle

    f, k = store._file("candles", symbol, src), tf_ms(dst)   # noqa: SLF001
    need = k // tf_ms(src)
    rows = duckdb.connect().execute(
        "SELECT t // ? * ? AS g, arg_min(o, t), max(h), min(l), arg_max(c, t), sum(v), "
        "sum(taker_buy_v), sum(trades) FROM read_parquet(?, hive_partitioning=false) "
        "GROUP BY 1 HAVING count(*) = ? ORDER BY 1", [k, k, f.as_posix(), need]).fetchall()
    store.upsert_candles(symbol, dst, [Candle(t=int(g), o=o, h=h, l=lo, c=c, v=v, taker_buy_v=tb,
                                              trades=None if n is None else int(n))
                                       for g, o, h, lo, c, v, tb, n in rows],
                         f"agregado de {src}")
    return len(rows)


def _ms(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)


def nfi_adapter(data: Path):
    """NFI (modo B) si el entorno aparte y el checkout están preparados; si no, None."""
    py, engine = os.environ.get(FT_PY_ENV), os.environ.get(FT_ENGINE_ENV)
    checkout = Path(os.environ.get(NFI_DIR_ENV) or data / "bots" / "nostalgia-for-infinity")
    if not (py and engine and checkout.exists()):
        return None
    from eim.bots.nfi_adapter import NfiAdapter

    return NfiAdapter(Path(py), checkout, engine)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eim.bots.backfill", description=__doc__)
    p.add_argument("--data-dir", default=os.environ.get("EIM_DATA_DIR", "data"))
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--timeframe", default="1h", choices=["1h", "5m"])
    p.add_argument("--since", required=True, help="primer día (UTC, AAAA-MM-DD) con posturas")
    a = p.parse_args(argv)
    data, tf = Path(a.data_dir), a.timeframe
    store, from_asof = Store(data), _ms(a.since)
    if tf == "5m" and store.bounds(a.symbol, "5m") is None:
        print("5m agregado desde 1m:", aggregate(store, a.symbol), "velas")
    reports = ReportStore(data / "reports.duckdb")
    sigs = BotSignalStore(*reports.connection)
    now = int(time.time() * 1000)
    if tf == "5m":
        return _backfill_nfi(data, store, sigs, a.symbol, from_asof, now)
    candles = store.read_candles(a.symbol, tf)
    adapters = [HummingbotDirectionalAdapter(), JesseExamplesAdapter(), TrendRiderAdapter()]
    history = max([HISTORY_BARS, *(getattr(x, "history_bars", 0) for x in adapters)])
    if not candles or candles[0].t + history * tf_ms(tf) > from_asof:
        print("el almacén no cubre la ventana pedida más las velas previas de calentamiento")
        return 2
    service = BotService(adapters, sigs, clock=lambda: now)
    n = 0
    for snap in snapshots(candles, a.symbol, tf, from_asof, history):
        n += sum(1 for s in service.produce(snap) if s.status == "ok")
    print("modo A (hummingbot, jesse, trendrider):", n, "señales ok")
    py, engine = os.environ.get(FT_PY_ENV), os.environ.get(FT_ENGINE_ENV)
    checkout = data / "bots" / "freqtrade-strategies"
    if py and engine and checkout.exists():
        from eim.bots.ft_adapter import FreqtradeAdapter

        ft = FreqtradeAdapter(Path(py), checkout, engine)
        print("freqtrade-strategies:", backfill_ft(sigs, ft, candles, a.symbol, tf, from_asof, now))
    else:
        print("freqtrade-strategies: sin entorno aparte (EIM_BOT_FREQTRADE_*): no se rellena")
    return 0


def _backfill_nfi(data: Path, store: Store, sigs: BotSignalStore, symbol: str, from_asof: int,
                  now: int) -> int:
    nfi = nfi_adapter(data)
    if nfi is None:
        print("nostalgia-for-infinity: sin entorno aparte ni checkout (EIM_BOT_FREQTRADE_*, "
              f"{NFI_DIR_ENV}): no se rellena")
        return 2
    step = tf_ms("5m")
    first = from_asof - (nfi.warm + 5) * step
    candles = store.read_candles(symbol, "5m", start=first)
    if not candles or candles[0].t > first + 12 * step:
        print(f"el almacén de 5m no cubre la ventana pedida más el arranque de NFI ({nfi.warm})")
        return 2
    info_from = first - INFO_DAYS * 86_400_000
    tfs = {tf: store.read_candles(symbol, tf, start=info_from) for tf in ("15m", "1h")}
    if not tfs["1h"] or tfs["1h"][0].t > info_from + 3_600_000 * 12:
        print(f"el almacén de 1h no cubre los {INFO_DAYS} días previos que pide el diario de NFI")
        return 2
    print("nostalgia-for-infinity:",
          backfill_ft(sigs, nfi, candles, symbol, "5m", from_asof, now, tfs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
