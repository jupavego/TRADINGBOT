"""API del escuadrón de bots (T57): el agente aparece con su evidencia y las señales se guardan."""

import time

import pytest

from eim.api.config import Settings
from eim.api.main import create_app
from eim.data.store import Store
from tests.api.test_api import STEP, FakeSource, _candles
from tests.local_client import LocalClient


@pytest.fixture
def client(tmp_path):
    hist = _candles(300)
    Store(tmp_path).upsert_candles("ETHUSDT", "1h", hist, "test")
    from eim.core import Candle
    nxt = Candle(t=hist[-1].t + STEP, o=2200, h=2210, l=2190, c=2205, v=50)
    cfg = Settings(data_dir=tmp_path, heartbeat_s=0.2, snapshot_bars=300)
    with LocalClient(create_app(cfg, source=FakeSource(nxt))) as c:
        yield c


def _analyze(client):
    with client.websocket_connect("/v2/stream?symbol=ETHUSDT&tf=1h") as ws:
        deadline = time.monotonic() + 90
        got = []
        while time.monotonic() < deadline:
            msg = ws.receive_json()
            if msg["type"] == "heartbeat":
                continue
            got.append(msg)
            if msg["type"] == "reports" and any(m["type"] == "tick" and m["closed"] for m in got):
                return msg
    pytest.fail("sin reportes")


def test_agent_listed_with_context_role_and_no_weight(client):
    ag = {a["id"]: a for a in client.get("/v2/agents").json()}
    assert ag["bots"]["role"] == "contexto" and ag["bots"]["weight"] is None
    assert ag["bots"]["requires"] == ["bot_signals"] and ag["bots"]["status"] == "sin_ejecutar"


def test_after_a_run_the_agent_has_evidence_and_signals_are_persisted(client):
    rep = _analyze(client)
    bots = next(r for r in rep["reports"] if r["agent_id"] == "bots")
    assert bots["status"] == "ok" and bots["bias"] == 0 and bots["confidence"] == 0
    assert {b["strategy"] for b in bots["metrics"]["bots"]} == {"bollinger_v1", "macd_bb_v1"}
    assert bots["evidence"] and all(b["votes"] is False for b in bots["metrics"]["bots"])
    ag = {a["id"]: a for a in client.get("/v2/agents").json()}
    assert ag["bots"]["last_asof"] == rep["asof"] and ag["bots"]["status"] == "ok"
    saved = client.get("/v2/bots/signals", params={"symbol": "ETHUSDT", "tf": "1h"}).json()
    assert saved["signals"], "bot_signals vacío"
    assert {s["asof"] for s in saved["signals"]} >= {rep["asof"]}
    last = [s for s in saved["signals"] if s["asof"] == rep["asof"]]
    assert {s["strategy"] for s in last} == {"bollinger_v1", "macd_bb_v1"}
    assert all(s["data_quality"]["last_candle_t"] <= s["asof"] and len(s["version"]) == 53
               for s in last)
    # el agente no entra en la síntesis
    syn = rep["synthesis"]
    assert syn is None or "bots" not in syn["contributions"]


def test_signals_route_validates_and_catalog_lists_only_usable(client):
    assert client.get("/v2/bots/signals", params={"symbol": "XXX"}).status_code == 400
    cat = client.get("/v2/bots/catalog").json()
    assert {b["id"] for b in cat["bots"]} == {
        "hummingbot-directional", "freqtrade", "freqtrade-strategies", "passivbot"}
    active = {b["id"] for b in cat["bots"] if b["adapter_active"]}
    assert active == {"hummingbot-directional"}            # B solo si hay entorno configurado
    assert "no tienen voto" in cat["mode"]


def test_scorecard_route_is_read_only_and_simulated(client):
    r = client.get("/v2/bots/scorecard", params={"symbol": "ETHUSDT"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "SIMULADO" and "bots" in body
    assert client.get("/v2/bots/scorecard", params={"symbol": "XXX"}).status_code == 400
    assert client.post("/v2/bots/scorecard").status_code in (404, 405)


def test_squad_endpoint_lists_real_bots_with_label_and_no_orders(client):
    rep = _analyze(client)
    r = client.get("/v2/bots", params={"symbol": "ETHUSDT", "tf": "1h"}).json()
    assert r["label"] == "Señal de un bot externo · no es una operación"
    assert r["mode"].startswith("ANALISIS") and r["channels"]["second_opinion"] is True
    assert {b["strategy"] for b in r["bots"]} == {"bollinger_v1", "macd_bb_v1"}
    assert all(b["votes"] is False and b["asof"] == rep["asof"] for b in r["bots"])
    assert all(not {"size", "qty", "leverage", "order"} & set(b) for b in r["bots"])
    assert r["support"]["total"] == len(r["bots"])
    assert client.get("/v2/bots", params={"symbol": "XXX"}).status_code == 400
    assert client.post("/v2/bots", headers={"X-EIM-Confirm": "1"}).status_code in (404, 405)
