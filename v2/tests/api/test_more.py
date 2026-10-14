"""Endpoints `/v2/more/*` con fuentes simuladas (sin red) + regresión de la bitácora vs legado."""
from __future__ import annotations

import io
from datetime import UTC, datetime

import pandas as pd
import pytest

from eim.api.config import Settings
from eim.api.main import create_app
from eim.api.more import MoreSources
from eim.core import Candle, LiquidationDay, Liquidations
from eim.data.store import Store
from tests.api.test_api import FakeSource, _candles
from tests.legacy import _runner as r
from tests.local_client import LocalClient

MONTH = [Candle(t=int(datetime(2020 + i // 12, i % 12 + 1, 1, tzinfo=UTC).timestamp() * 1000),
                o=100 + i, h=200 + i * 2, l=90 + i, c=100 + i * 2, v=1) for i in range(40)]


def _liq(stale: bool) -> Liquidations:
    return Liquidations(
        requested_symbol="ETHUSDT", liquidation_symbol="ETHUSD_PERP", most_recent_date="2024-10-14",
        stale=stale, stale_age_days=700, days_with_data=1, source="test",
        daily=[LiquidationDay(t=1_728_864_000_000, longs_usd=5, shorts_usd=3)])


@pytest.fixture
def client(tmp_path):
    Store(tmp_path).upsert_candles("ETHUSDT", "1h", _candles(1200), "test")
    more = MoreSources(
        liquidations=lambda s, d, b: _liq(True),
        ohlcv=lambda a, tf, n: (MONTH[:n], "fuente-prueba"),
        monthly=lambda a, y: (MONTH, "fuente-prueba"))
    cfg = Settings(data_dir=tmp_path, heartbeat_s=0.2, snapshot_bars=300)
    with LocalClient(create_app(cfg, source=FakeSource(_candles(1)[0]), more=more)) as c:
        yield c


def test_assets_and_multi_asset(client):
    keys = {a["key"] for a in client.get("/v2/more/assets").json()["assets"]}
    assert keys >= {"SP500", "XAUUSDT"}
    j = client.get("/v2/more/multi-asset", params={"asset": "SP500", "tf": "1d", "n": 20}).json()
    assert j["source"] == "fuente-prueba" and len(j["candles"]) == 20 and j["coverage"]
    assert client.get("/v2/more/multi-asset", params={"asset": "NOPE"}).status_code == 400


def test_seasonality_exposes_real_coverage(client):
    j = client.get("/v2/more/seasonality", params={"asset": "ETHUSDT", "start_year": 2020}).json()
    assert j["real_data_range"]["start"] == "2020-01" and j["source"] == "fuente-prueba"
    assert j["rows"][0]["year"] == 2020 and j["rows"][0]["Ene"] is None  # sin retorno previo
    assert j["monthly_average_pct"]["Feb"] is not None


def test_liquidations_keeps_stale_flag(client):
    j = client.get("/v2/more/liquidations").json()
    assert j["stale"] is True and j["liquidation_symbol"] == "ETHUSD_PERP"


def test_vwap_periods(client):
    j = client.get("/v2/more/vwap-periods", params={"n": 200}).json()
    assert set(j["current"]) == {"daily", "weekly", "quincenal", "monthly"}
    assert len(j["series"]["daily"]) == 200 and j["source"] == "test"
    assert j["current"]["daily"]["position"]


def test_backtest_endpoint(client):
    j = client.get("/v2/more/backtest", params={"candles": 1000, "horizon": 6}).json()
    assert j["total_evaluated"] > 0 and j["source"] == "test"
    assert j["acceptance_criteria"]["criteria"]["CA-009"]["status"] == "NO_EVALUADO"
    assert client.get("/v2/more/backtest", params={"symbol": "BTCUSDT"}).status_code == 400


def _xlsx() -> bytes:
    cols = ["Uid", "Hora", "Símbolo", "Lado", "Precio", "Cantidad", "Cantidad",
            "Ganancia Realizada", "Comisión"]
    rows = [[1, "2026-01-01 10:00:00", "ETHUSDT", "BUY", 100.0, 1.0, 100.0, 0.0, 0.05],
            [1, "2026-01-01 12:30:00", "ETHUSDT", "SELL", 110.0, 1.0, 110.0, 10.0, 0.055],
            [1, "2026-01-02 09:00:00", "ETHUSDT", "SELL", 120.0, 2.0, 240.0, 0.0, 0.1],
            [1, "2026-01-02 15:00:00", "ETHUSDT", "BUY", 130.0, 2.0, 260.0, -20.0, 0.1]]
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=cols).to_excel(buf, index=False)
    return buf.getvalue()


def test_bitacora_matches_legacy_and_requires_leverage(client):
    files = {"file": ("x.xlsx", _xlsx(), "application/octet-stream")}
    assert client.post("/v2/more/bitacora", files=files).status_code == 422  # sin apalancamiento
    ok = client.post("/v2/more/bitacora", files=files, data={"leverage": 10})
    assert ok.status_code == 200, ok.text
    j = ok.json()
    r._legacy_path()
    from eim_bitacora import build_bitacora as legacy

    from eim.api.more import jsonable
    assert j == jsonable(legacy(_xlsx(), leverage=10))
    assert {t["pnl_source"] for t in j["trades"]} == {"trading_history"}
    bad = client.post("/v2/more/bitacora", files={"file": ("x.csv", b"a", "text/csv")},
                      data={"leverage": 10})
    assert bad.status_code == 400



def test_bitacora_body_limit(client):
    from eim.api.security import MAX_BODY_BYTES
    big = {"file": ("x.xlsx", b"0" * (MAX_BODY_BYTES + 1), "application/octet-stream")}
    assert client.post("/v2/more/bitacora", files=big, data={"leverage": 10}).status_code == 413
