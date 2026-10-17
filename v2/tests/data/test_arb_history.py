"""Histórico de arbitraje (T43): almacén spot separado, calendario de trimestrales,
precio de liquidación y carga sin red."""

from __future__ import annotations

from pathlib import Path

from eim.core import Candle
from eim.data.arb_history import load_history
from eim.data.arb_history_sync import quarterly_deliveries, quarterly_symbol
from eim.data.store import Store
from eim.data.timeframes import TF_MS, tf_ms

H = 3_600_000
D = 1_719_561_600_000  # 2024-06-28 08:00 UTC (BTCUSDT_240628)


def _c(t: int, px: float, v: float = 1.0, lo: float | None = None) -> Candle:
    return Candle(t=t, o=px, h=px, l=px if lo is None else lo, c=px, v=v)


def test_spot_kind_is_separate_from_futures(tmp_path: Path):
    st = Store(tmp_path)
    st.upsert_candles("BTCUSDT", "1h", [_c(0, 1.0)], "fut")
    st.upsert_candles("BTCUSDT", "1h", [_c(0, 2.0), _c(H, 3.0)], "spot", kind="spot_candles")
    assert [k.c for k in st.read_candles("BTCUSDT", "1h")] == [1.0]
    assert [k.c for k in st.read_candles("BTCUSDT", "1h", kind="spot_candles")] == [2.0, 3.0]
    assert st.bounds("BTCUSDT", "1h", "spot_candles") == (0, H)


def test_one_minute_is_store_only():
    assert tf_ms("1m") == 60_000 and "1m" not in TF_MS  # la API no lo expone


def test_quarterly_calendar_is_last_friday_0800_utc():
    ds = quarterly_deliveries(1_704_067_200_000, 1_735_603_200_000)  # 2024
    syms = [quarterly_symbol("BTC", d) for d in ds]
    assert syms[:4] == ["BTCUSDT_240329", "BTCUSDT_240628", "BTCUSDT_240927", "BTCUSDT_241227"]
    assert D in ds


def test_settlement_from_flat_bar_else_approximate(tmp_path: Path):
    st = Store(tmp_path)
    before = [_c(D - k * H, 61_500.0, lo=61_400.0) for k in range(5, 0, -1)]
    st.upsert_candles("BTCUSDT_240628", "1h", [*before, _c(D, 61_440.0, v=0.0)], "binance")
    st.upsert_candles("BTCUSDT_240927", "1h",
                      [_c(D + 80 * 24 * H, 65_000.0), _c(1_727_424_000_000, 65_426.0, v=2.0,
                                                          lo=65_400.0)], "binance")
    hist = load_history(st, tmp_path, assets=("BTC",), start=D - 10 * H,
                        end=1_727_424_000_000 + 5 * H, tri=False)
    qs = {q.symbol: q for q in hist.assets["BTC"].quarterlies}
    q = qs["BTCUSDT_240628"]
    assert q.settle == 61_440.0 and "plana" in q.settle_source
    assert len(q.bars) == 5 and int(q.bars.t[-1]) < D  # solo velas antes del vencimiento
    q2 = qs["BTCUSDT_240927"]
    assert q2.settle == 65_426.0 and "aprox" in q2.settle_source
    assert "settle:BTCUSDT_240927" in hist.missing
    assert "depth" in hist.missing and "spot:BTCUSDT" in hist.missing  # declarado, no inventado
