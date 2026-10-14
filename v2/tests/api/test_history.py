"""Carga automática de historia para marcos vacíos (sin red: proveedor falso)."""
from __future__ import annotations

from eim.api.config import Settings
from eim.api.history import HistoryLoader
from eim.api.main import create_app
from eim.core import Candle
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from tests.local_client import LocalClient


class FakeProvider:
    name = "fake"

    def klines(self, symbol, timeframe, start, end):
        step = tf_ms(timeframe)
        t0 = start - start % step
        return [Candle(t=t, o=100.0, h=101.0, l=99.0, c=100.5, v=1.0)
                for t in range(t0, end - step, step)]


def test_empty_timeframe_is_filled_and_served(tmp_path):
    store = Store(tmp_path)
    loader = HistoryLoader(store, FakeProvider(), bars=700, min_bars=600)
    app = create_app(Settings(data_dir=tmp_path), history=loader)
    with LocalClient(app) as client:
        r = client.get("/v2/snapshot", params={"symbol": "BTCUSDT", "tf": "4h", "n": 50})
        assert r.status_code == 200 and len(r.json()["candles"]) == 50


def test_network_failure_does_not_raise(tmp_path):
    class Boom:
        name = "boom"

        def klines(self, *a):
            raise RuntimeError("sin red")

    loader = HistoryLoader(Store(tmp_path), Boom())
    assert loader.ensure("BTCUSDT", "4h") is False
    assert "sin red" in loader.errors[("BTCUSDT", "4h")]
