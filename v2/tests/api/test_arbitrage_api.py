"""API del escáner de arbitraje (T39) sobre el fixture real de Binance (sin red)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eim.api.config import Settings
from eim.api.main import create_app
from eim.arbitrage import scan_all
from eim.arbitrage.alerts import AlertParams, AlertTracker
from eim.core import ArbMarket
from eim.data.arb_store import ArbStore
from tests.api.test_api import STEP, FakeSource, _candles
from tests.local_client import LocalClient

FIXTURE = Path(__file__).parents[1] / "fixtures" / "arbitrage" / "binance_arb_2026-10-15.json"
MKT = ArbMarket.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
URL = "/v2/arbitrage/opportunities"


def _client(tmp_path, with_scan: bool):
    if with_scan:
        ArbStore(tmp_path).save(MKT)
    nxt = _candles(1)[0].model_copy(update={"t": _candles(1)[0].t + STEP})
    # La fixture se capturó con BTC y ETH y aquí se mide la paridad con el motor completo; el foco
    # del sistema es solo BTC (T122), así que los activos se declaran explícitamente.
    app = create_app(Settings(data_dir=tmp_path, heartbeat_s=0.2, arb_assets=("BTC", "ETH")),
                     source=FakeSource(nxt))
    app.state.arb_desk.clock = lambda: MKT.asof + 3000
    return LocalClient(app)


@pytest.fixture
def client(tmp_path):
    with _client(tmp_path, with_scan=True) as c:
        yield c


def test_without_scan_is_no_data_but_mode_visible(tmp_path):
    with _client(tmp_path, with_scan=False) as c:
        body = c.get(URL).json()
    assert body["mode"] == "ANALISIS" and body["label"] == "neto estimado, no garantizado"
    assert body["report"]["status"] == "no_data" and body["report"]["bias"] == 0
    assert body["opportunities"] == [] and body["stale"] is True and body["scan_asof"] is None


def test_opportunities_match_engine_breakdown(client):
    body = client.get(URL).json()
    assert body["mode"] == "ANALISIS" and body["type"] == "arbitrage"
    assert body["scan_asof"] == MKT.asof and body["age_s"] == 3.0 and body["stale"] is False
    ref = scan_all(MKT).selection
    rows = body["opportunities"]
    assert len(rows) == len(ref.selected) + len(ref.rejected) == 28
    exp = ([r.opportunity for r in ref.selected] + [r.opportunity for r in ref.rejected])
    for row, o in zip(rows, exp, strict=True):
        assert (row["strategy"], row["variant"], row["asset"]) == (o.strategy, o.variant, o.asset)
        assert row["net"] == o.net_edge and row["gross"] == o.gross_edge
        assert row["costs"] == {"fees": o.costs.fees, "slippage": o.costs.slippage,
                                "funding": o.costs.funding, "borrow": o.costs.borrow,
                                "total": o.costs.total}
        assert row["capital"] == o.capital_required and row["annualized"] == o.annualized
        assert len(row["legs"]) == len(o.legs) and row["legs"][0]["vwap"] == o.legs[0].vwap
        assert row["valid_until"] == o.valid_until
    sel = [r for r in rows if r["selected"]]
    assert len(sel) == len(ref.selected) and all(r["score"] is not None for r in sel)
    assert all(r["reason"] and r["reject_code"] for r in rows if not r["selected"])
    assert len({r["id"] for r in rows}) == len(rows)
    rep = body["report"]
    assert rep["agent_id"] == "arbitrage" and rep["bias"] == 0 and rep["status"] == "ok"
    assert rep["metrics"]["mode"] == "ANALISIS"
    assert set(rep["metrics"]["funding"]) == {"BTCUSDT", "ETHUSDT", "BTCUSDC", "ETHUSDC"}
    assert body["alerts"] == []  # cash-and-carry ≈ 3 % anual: < 3 pb/día


def test_alerts_flow_through_the_endpoint(client):
    desk = client.app.state.arb_desk
    desk.tracker = AlertTracker(AlertParams(min_score=0, hold_s=0))
    alerts = client.get(URL).json()["alerts"]
    assert alerts and all(a["active"] and a["new"] for a in alerts)
    again = client.get(URL).json()["alerts"]  # mismo escaneo: no se repite el aviso nuevo
    assert again == alerts


def test_snapshot_does_not_ship_books(client):
    client.app.state.store.upsert_candles("ETHUSDT", "1h", _candles(50), "test")
    snap = client.get("/v2/snapshot", params={"symbol": "ETHUSDT", "tf": "1h"}).json()
    assert "arb" not in snap


def test_ws_receives_arbitrage_message(client):
    app = client.app
    with client.websocket_connect("/v2/stream?symbol=BTCUSDT&tf=4h") as ws:
        ws.receive_json()  # estado inicial
        client.portal.call(app.state.hub.broadcast_all, app.state.arb_desk.payload())
        msg = next(m for m in (ws.receive_json() for _ in range(50)) if m["type"] == "arbitrage")
    assert msg["mode"] == "ANALISIS" and len(msg["opportunities"]) == 28
    assert msg["report"]["bias"] == 0
