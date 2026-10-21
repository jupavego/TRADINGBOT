"""Carga de historia de un símbolo nuevo con un proveedor falso (sin red)."""

from eim.core import Candle
from eim.data import Store
from eim.data.backfill import backfill_symbol
from eim.data.timeframes import TF_MS, tf_ms

NOW = 1_792_560_000_000


class FakeProvider:
    name = "fake"

    def klines(self, symbol, timeframe, start, end):
        step = tf_ms(timeframe)
        t = start + (-start) % step
        out = []
        while t + step <= end:
            out.append(Candle(t=t, o=100.0, h=101.0, l=99.0, c=100.5, v=1.0))
            t += step
        return out

    def funding_rates(self, symbol, start, end):
        eight_h = 28_800_000
        return [(t, 0.0001) for t in range(start - start % eight_h + eight_h, end, eight_h)]

    def open_interest(self, symbol, timeframe, start, end):
        raise RuntimeError("fuera de retención")        # un derivado que falla no frena la carga


def test_backfill_fills_every_timeframe_and_is_incremental(tmp_path):
    st = Store(tmp_path)
    res = backfill_symbol(st, FakeProvider(), "ETHUSDT", bars=300, now=NOW)
    assert set(res) == set(TF_MS)
    for tf in TF_MS:
        assert res[tf]["candles"]["total"] >= 299 and res[tf]["candles"]["gaps"] == 0
        assert "error" in res[tf]["derivatives"]          # OI falló y se informa, sin inventar
    again = backfill_symbol(st, FakeProvider(), "ETHUSDT", bars=300, now=NOW)
    assert all(again[tf]["candles"]["fetched"] == 0 for tf in TF_MS)   # nada nuevo que bajar
