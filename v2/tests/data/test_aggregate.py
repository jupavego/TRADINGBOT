"""Agregación 1m → 5m (solo de almacén): completa e incremental, sin velas a medias."""

from eim.core import Candle
from eim.data.aggregate import aggregate, aggregate_new
from eim.data.store import Store

M = 60_000


def minute(i: int, t0: int = 0) -> Candle:
    return Candle(t=t0 + i * M, o=100 + i, h=102 + i, l=99 + i, c=101 + i, v=1.0,
                  taker_buy_v=0.5, trades=3)


def test_full_then_incremental_equals_one_pass(tmp_path):
    st = Store(tmp_path)
    st.upsert_candles("BTCUSDT", "1m", [minute(i) for i in range(60)], "t")
    assert aggregate(st, "BTCUSDT") == 12
    first = st.read_candles("BTCUSDT", "5m")
    assert [c.t for c in first] == [k * 5 * M for k in range(12)]
    c0 = first[0]
    assert (c0.o, c0.h, c0.l, c0.c) == (100, 106, 99, 105)
    assert (c0.v, c0.taker_buy_v, c0.trades) == (5, 2.5, 15)

    # llegan 1m nuevos (el último grupo queda incompleto): solo se agregan los completos
    st.upsert_candles("BTCUSDT", "1m", [minute(i) for i in range(60, 83)], "t")
    assert aggregate_new(st, "BTCUSDT") >= 4
    got = st.read_candles("BTCUSDT", "5m")
    assert got[-1].t == 15 * 5 * M                             # el grupo 16 (3 min) no entra
    ref = Store(tmp_path / "ref")
    ref.upsert_candles("BTCUSDT", "1m", [minute(i) for i in range(83)], "t")
    aggregate(ref, "BTCUSDT")
    assert got == ref.read_candles("BTCUSDT", "5m")


def test_incremental_heals_a_late_filled_gap(tmp_path):
    st = Store(tmp_path)
    mins = [minute(i) for i in range(30) if i != 7]            # falta el minuto 7
    st.upsert_candles("BTCUSDT", "1m", mins, "t")
    aggregate(st, "BTCUSDT")
    assert 5 * M not in [c.t for c in st.read_candles("BTCUSDT", "5m")]
    st.upsert_candles("BTCUSDT", "1m", [minute(7)], "t")      # llega tarde
    aggregate_new(st, "BTCUSDT")
    assert 5 * M in [c.t for c in st.read_candles("BTCUSDT", "5m")]


def test_nothing_to_aggregate_is_zero(tmp_path):
    assert aggregate(Store(tmp_path), "BTCUSDT") == 0
