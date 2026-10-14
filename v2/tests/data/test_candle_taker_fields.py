"""T34: campos opcionales `taker_buy_v` y `trades` en proveedor, stream y almacén (sin red)."""

from __future__ import annotations

import duckdb
import httpx

from eim.api.sources import parse_kline
from eim.core import Candle
from eim.data import Store
from eim.data.providers import BinanceFutures

H = 3_600_000
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H)
NOW = T0 + 100 * H


def _row(t: int) -> list:
    # formato completo de /fapi/v1/klines: 12 campos
    return [t, "100", "102", "99", "101", "10.5", t + H - 1, "1060.5", 42, "6.25", "631.0", "0"]


def test_provider_parses_taker_buy_and_trades():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_row(T0), _row(T0 + H)])

    client = httpx.Client(base_url="https://fapi.binance.com",
                          transport=httpx.MockTransport(handler))
    prov = BinanceFutures(client, sleep=lambda s: None, clock=lambda: NOW)
    out = prov.klines("BTCUSDT", "1h", T0, T0 + 2 * H)
    assert [c.taker_buy_v for c in out] == [6.25, 6.25]
    assert [c.trades for c in out] == [42, 42]


def test_parse_kline_reads_taker_fields():
    msg = {"k": {"t": T0, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "9",
                 "V": "4", "n": 7, "x": True}}
    c, closed = parse_kline(msg)
    assert closed and c.taker_buy_v == 4.0 and c.trades == 7


def test_store_roundtrip_and_legacy_files(tmp_path):
    store = Store(tmp_path)
    f = tmp_path / "candles" / "symbol=BTCUSDT" / "timeframe=1h" / "data.parquet"
    f.parent.mkdir(parents=True)
    # archivo previo a T34: sin columnas taker_buy_v / trades
    duckdb.connect().execute(
        f"COPY (SELECT {T0}::BIGINT AS t, 1.0 AS o, 2.0 AS h, 0.5 AS l, 1.5 AS c, 9.0 AS v) "
        f"TO '{f.as_posix()}' (FORMAT PARQUET)"
    )
    old = store.read_candles("BTCUSDT", "1h")
    assert old == [Candle(t=T0, o=1, h=2, l=0.5, c=1.5, v=9)]  # opcionales → None

    new = Candle(t=T0 + H, o=1.5, h=2, l=1, c=1.8, v=8, taker_buy_v=5, trades=11)
    assert store.upsert_candles("BTCUSDT", "1h", [new], "binance-futures") == 2
    got = store.read_candles("BTCUSDT", "1h")
    assert got[0].taker_buy_v is None and got[0].trades is None
    assert got[1] == new
