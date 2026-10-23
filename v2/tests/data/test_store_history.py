"""Almacén en dos tramos: histórico congelado + vivo (historia de 1 min sin reescribirla a cada
vela, BACKLOG T111 (1)). Sin red."""

from __future__ import annotations

import numpy as np
import pytest

from eim.core import Candle
from eim.data import import_history
from eim.data.aggregate import aggregate
from eim.data.store import HISTORY, LIVE, Store
from eim.data.sync import sync_candles
from eim.paper.engine import Path

M = 60_000
T0 = 1_700_000_040_000 // (5 * M) * (5 * M)


def bars(a: int, b: int, px: float = 100.0) -> list[Candle]:
    return [Candle(t=T0 + k * M, o=px + k, h=px + k + 1, l=px + k - 1, c=px + k + 0.5, v=1.0)
            for k in range(a, b)]


def files(st: Store) -> dict[str, float]:
    d = st._dir("candles", "BTCUSDT", "1m")
    return {p.name: p.stat().st_mtime_ns for p in d.glob("*.parquet")}


def test_history_and_live_read_as_one_series_and_live_wins(tmp_path):
    st = Store(tmp_path)
    st.upsert_candles("BTCUSDT", "1m", bars(100, 110), "vivo")
    n = st.add_history("BTCUSDT", "1m", bars(0, 105, px=999.0), "historia")
    assert n == 100                                    # solo lo anterior a la primera vela viva
    cs = st.read_candles("BTCUSDT", "1m")
    assert [c.t for c in cs] == [T0 + k * M for k in range(110)]
    assert cs[99].o == 999.0 + 99 and cs[100].o == 100.0 + 100   # lo vivo no se tapa
    assert st.bounds("BTCUSDT", "1m") == (T0, T0 + 109 * M)
    assert st.count("BTCUSDT", "1m") == 110
    assert st.source("candles", "BTCUSDT", "1m") == "vivo"
    assert [c.t for c in st.read_candles("BTCUSDT", "1m", last=3)] == [
        T0 + k * M for k in (107, 108, 109)]
    assert len(st.read_candles("BTCUSDT", "1m", start=T0 + 98 * M, end=T0 + 102 * M)) == 4


def test_history_can_be_copied_from_another_store_with_sql(tmp_path):
    src, dst = Store(tmp_path / "copia"), Store(tmp_path / "vivo")
    src.upsert_candles("BTCUSDT", "1m", bars(0, 30, px=50.0), "copia")
    dst.upsert_candles("BTCUSDT", "1m", bars(20, 25), "vivo")
    assert dst.add_history("BTCUSDT", "1m", src, "binance-futures") == 20   # antes de lo vivo
    got = dst.read_candles("BTCUSDT", "1m")
    assert [c.t for c in got] == [T0 + k * M for k in range(25)]
    assert got[19].o == 50.0 + 19 and got[20].o == 100.0 + 20
    assert Store(tmp_path / "nada").add_history("BTCUSDT", "1m", src, "x") == 30


def test_import_history_cli(tmp_path, capsys):
    src, dst = Store(tmp_path / "copia"), Store(tmp_path / "data")
    src.upsert_candles("BTCUSDT", "1m", bars(0, 30), "copia")
    dst.upsert_candles("BTCUSDT", "1m", bars(25, 30), "vivo")
    args = ["--from", str(tmp_path / "copia"), "--data", str(tmp_path / "data")]
    assert import_history.main(args) == 0 and import_history.main(args) == 0   # idempotente
    assert dst.count("BTCUSDT", "1m") == 30 and "25 velas" in capsys.readouterr().out
    assert import_history.main(["--from", str(tmp_path / "nada")]) == 1


def test_upserts_never_rewrite_the_history_file(tmp_path):
    st = Store(tmp_path)
    st.upsert_candles("BTCUSDT", "1m", bars(100, 101), "vivo")
    st.add_history("BTCUSDT", "1m", bars(0, 100), "historia")
    before = files(st)
    total = st.upsert_candles("BTCUSDT", "1m", bars(101, 103), "vivo")
    after = files(st)
    assert after[HISTORY] == before[HISTORY] and after[LIVE] != before[LIVE]
    assert total == 103 == st.count("BTCUSDT", "1m")


def test_gaps_and_arrays_span_both_parts(tmp_path):
    st = Store(tmp_path)
    st.upsert_candles("BTCUSDT", "1m", bars(60, 70), "vivo")
    st.add_history("BTCUSDT", "1m", bars(0, 20) + bars(30, 50), "historia")
    assert st.find_gaps("BTCUSDT", "1m") == [(T0 + 20 * M, T0 + 29 * M),
                                             (T0 + 50 * M, T0 + 59 * M)]
    a = st.read_arrays("BTCUSDT", "1m", start=T0 + 45 * M)
    cs = st.read_candles("BTCUSDT", "1m", start=T0 + 45 * M)
    assert a["t"].dtype == np.int64 and list(a["t"]) == [c.t for c in cs]
    assert list(a["c"]) == [c.c for c in cs]
    p = Path.from_arrays(a, M)
    q = Path(cs, (), M)
    assert np.array_equal(p.t, q.t) and np.array_equal(p.l, q.l) and p.end == q.end
    assert st.read_arrays("ETHUSDT", "1m")["t"].size == 0


def test_compact_moves_old_live_rows_without_losing_any(tmp_path):
    st = Store(tmp_path)
    st.upsert_candles("BTCUSDT", "1m", bars(0, 50), "vivo")
    assert st.compact("BTCUSDT", "1m", keep_ms=10 * M, min_rows=60) == 0   # aún pequeño
    whole = st.read_candles("BTCUSDT", "1m")
    assert st.compact("BTCUSDT", "1m", keep_ms=10 * M, min_rows=20) == 39
    assert st.read_candles("BTCUSDT", "1m") == whole
    assert [p.name for p in st._parts("candles", "BTCUSDT", "1m")] == [HISTORY, LIVE]
    assert len(Store(tmp_path).read_candles("BTCUSDT", "1m")) == 50   # otro lector ve lo mismo
    assert st.compact("BTCUSDT", "1m", keep_ms=10 * M, min_rows=20) == 0     # ya compactado
    st.upsert_candles("BTCUSDT", "1m", bars(50, 52), "vivo")
    assert st.count("BTCUSDT", "1m") == 52 and st.find_gaps("BTCUSDT", "1m") == []


def test_aggregate_reads_the_history_too(tmp_path):
    st = Store(tmp_path)
    st.upsert_candles("BTCUSDT", "1m", bars(10, 20), "vivo")
    st.add_history("BTCUSDT", "1m", bars(0, 10), "historia")
    assert aggregate(st, "BTCUSDT") == 4
    five = st.read_candles("BTCUSDT", "5m")
    assert [c.t for c in five] == [T0 + k * 5 * M for k in range(4)]
    assert five[1].o == 100.0 + 5 and five[1].c == 100.0 + 9.5


class _Prov:
    name = "prueba"

    def __init__(self, cs: list[Candle]) -> None:
        self.cs = cs

    def klines(self, symbol, timeframe, a, b):
        return [c for c in self.cs if a <= c.t < b]


def test_sync_fills_a_gap_inside_the_history_and_counts_both_parts(tmp_path):
    st = Store(tmp_path)
    st.upsert_candles("BTCUSDT", "1m", bars(40, 50), "vivo")
    st.add_history("BTCUSDT", "1m", bars(0, 15) + bars(20, 40), "historia")
    out = sync_candles(st, _Prov(bars(0, 52)), "BTCUSDT", "1m", T0 + 49 * M, T0 + 52 * M)
    assert out == {"fetched": 7, "total": 52, "gaps": 0}
    assert [c.t for c in st.read_candles("BTCUSDT", "1m")] == [T0 + k * M for k in range(52)]


def test_series_without_history_behave_as_before(tmp_path):
    st = Store(tmp_path)
    st.upsert_series("funding", "BTCUSDT", "-", [(1, 0.1), (2, 0.2)], "x")
    assert st.read_series("funding", "BTCUSDT") == [(1, 0.1), (2, 0.2)]
    assert st.bounds("BTCUSDT", "-", kind="funding") == (1, 2)
    with pytest.raises(ValueError):
        st.add_history("BTCUSDT", "7x", [], "x")
