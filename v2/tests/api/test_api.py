"""API con cliente de prueba y fuente simulada (sin red)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from eim.api.config import Settings
from eim.api.main import create_app
from eim.api.sources import LiveEvent, parse_kline
from eim.core import Candle
from eim.data.store import Store
from eim.data.timeframes import tf_ms

STEP = tf_ms("1h")
T0 = 1_700_000_000_000 // STEP * STEP


def _candles(n: int) -> list[Candle]:
    out = []
    for i in range(n):
        p = 2000 + i * 0.5 + (i % 7)
        out.append(Candle(t=T0 + i * STEP, o=p, h=p + 5, l=p - 5, c=p + 1, v=100 + i))
    return out


class FakeSource:
    name = "fake-ws"

    def __init__(self, next_candle: Candle) -> None:
        self.next = next_candle

    async def stream(self, symbol: str, timeframe: str) -> AsyncIterator[LiveEvent]:
        yield LiveEvent(type="status", state="up", detail="simulada")
        c = self.next
        yield LiveEvent(type="tick", candle=c, closed=False)
        yield LiveEvent(type="tick", candle=c, closed=True)
        await asyncio.sleep(3600)


@pytest.fixture
def client(tmp_path):
    hist = _candles(300)
    Store(tmp_path).upsert_candles("ETHUSDT", "1h", hist, "test")
    nxt = Candle(t=hist[-1].t + STEP, o=2200, h=2210, l=2190, c=2205, v=50)
    cfg = Settings(data_dir=tmp_path, heartbeat_s=0.2, snapshot_bars=300)
    with TestClient(create_app(cfg, source=FakeSource(nxt))) as c:
        yield c


def test_health_and_snapshot(client):
    assert client.get("/v2/health").json()["status"] == "ok"
    snap = client.get("/v2/snapshot", params={"symbol": "ETHUSDT", "tf": "1h", "n": 50}).json()
    assert len(snap["candles"]) == 50 and snap["sources"]["candles"] == "test"
    assert client.get("/v2/snapshot", params={"symbol": "XXX"}).status_code == 400
    assert client.get("/v2/snapshot", params={"symbol": "BTCUSDT"}).status_code == 404


def test_agents_listed_before_any_run(client):
    ag = client.get("/v2/agents").json()
    assert {"structure", "vwap"} <= {a["id"] for a in ag}
    assert all(a["status"] == "sin_ejecutar" for a in ag)


def test_stream_ticks_then_reports_persisted(client):
    got: list[dict] = []
    with client.websocket_connect("/v2/stream?symbol=ETHUSDT&tf=1h") as ws:
        for _ in range(16):
            msg = ws.receive_json()
            got.append(msg)
            # el primer "reports" es el análisis inicial (bootstrap); se espera el del cierre
            if msg["type"] == "reports" and any(m["type"] == "tick" and m["closed"] for m in got):
                break
    types = [m["type"] for m in got]
    assert "tick" in types and types[-1] == "reports"
    ticks = [m for m in got if m["type"] == "tick"]
    assert ticks[-1]["closed"] is True  # un cliente tardío recibe al menos el último tick
    rep = got[-1]
    assert rep["asof"] == ticks[-1]["candle"]["t"] + STEP
    assert len(rep["reports"]) >= 7 and isinstance(rep["overlays"], list)
    # persistidos y consultables por REST
    rows = client.get("/v2/reports", params={"symbol": "ETHUSDT", "tf": "1h"}).json()
    rows = [r for r in rows if r["asof"] == rep["asof"]]  # el bootstrap dejó filas más viejas
    assert {r["agent_id"] for r in rows} == {r["agent_id"] for r in rep["reports"]}
    rng = client.get("/v2/reports", params={"agent": "structure", "start": rep["asof"] + 1})
    assert rng.json() == []
    assert len(client.get("/v2/overlays").json()) == len(rep["overlays"])
    assert all(a["last_asof"] == rep["asof"] for a in client.get("/v2/agents").json())


def test_heartbeat_when_idle(client):
    with client.websocket_connect("/v2/stream?symbol=BTCUSDT&tf=15m") as ws:
        seen = {ws.receive_json()["type"] for _ in range(6)}
    assert "heartbeat" in seen or "reports" in seen


def test_stream_rejects_bad_params(client):
    with pytest.raises(Exception):  # noqa: B017
        with client.websocket_connect("/v2/stream?symbol=XXX&tf=1h"):
            pass


def test_parse_kline():
    msg = {"k": {"t": 1, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "9", "x": True}}
    c, closed = parse_kline(msg)
    assert closed and c.h == 2 and parse_kline({"e": "ping"}) is None


def test_cors_env(monkeypatch):
    monkeypatch.setenv("EIM_CORS_ORIGINS", "http://a.test, http://b.test")
    assert Settings.from_env().cors_origins == ("http://a.test", "http://b.test")


def test_bootstrap_publishes_reports_without_waiting_for_close(client):
    with client.websocket_connect("/v2/stream?symbol=ETHUSDT&tf=1h") as ws:
        first = next(m for m in (ws.receive_json() for _ in range(40)) if m["type"] == "reports")
    assert first["asof"] == T0 + 300 * STEP  # última vela almacenada + un marco
    assert len(first["reports"]) >= 7
    rows = client.get("/v2/reports", params={"symbol": "ETHUSDT", "tf": "1h"}).json()
    assert sum(1 for r in rows if r["asof"] == first["asof"]) >= 7
