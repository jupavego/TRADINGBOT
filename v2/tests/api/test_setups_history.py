"""`GET /v2/setups/history` (T51): publicadas + resolución, señal contra resultado, intervalos."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import eim.api.setups as api
from eim.api.setups import build_setups_router
from eim.core import Candle
from eim.data.paper_store import PaperStore
from eim.data.suggestion_store import SuggestionStore
from eim.paper.engine import Path
from eim.suggestions.tracker import Tracker
from tests.suggestions.helpers import NOW, PRICE, T1H, H, idea, verdict


def make(monkeypatch, ideas, verdicts):
    monkeypatch.setattr(api, "now_ms", lambda: NOW)
    cs = [Candle(t=NOW - (30 - k) * H, o=PRICE, h=PRICE + 1, l=PRICE - 1, c=PRICE, v=1.0)
          for k in range(30)]
    path = Path([Candle(t=T1H + k * 900_000, o=PRICE, h=PRICE + 3, l=PRICE - 0.5, c=PRICE, v=1.0)
                 for k in range(-1, 4)])
    view = SimpleNamespace(outcomes=[SimpleNamespace(idea=i, status="PENDIENTE", fill_t=None)
                                     for i in ideas],
                           stamp=(((1, T1H), (1, T1H), (1, T1H)),), path=path)
    desk = SimpleNamespace(store=SimpleNamespace(read_candles=lambda *a, **k: cs),
                           tfs=("15m", "1h", "4h"), symbols=("BTCUSDT",), last_tick=NOW - 30_000,
                           cached_view=lambda sym, wait_s=0.0: view,
                           view_state=lambda v: {"stale": False})
    validator = SimpleNamespace(
        crit=SimpleNamespace(version="validation_v1"),
        vstore=SimpleNamespace(latest=lambda c, s: (NOW - 2 * H, NOW - 2 * H, verdicts)))
    tracker = Tracker(SuggestionStore(PaperStore(":memory:")))
    app = FastAPI()
    router = build_setups_router(desk, validator, tracker=tracker)
    app.include_router(router)
    return TestClient(app), router


def test_publication_is_recorded_and_resolved(monkeypatch):
    c, _ = make(monkeypatch, [idea(sl_d=2.0, rr=1.0)], [verdict()])
    assert c.get("/v2/setups").json()["status"] == "ok"
    j = c.get("/v2/setups/history").json()
    assert j["mode"] == "ANALISIS" and j["totals"]["published"] == 1
    (p,) = j["published"]
    assert p["vid"] == "ema@1h@v1" and p["executed"] is False
    assert p["state"] == "sugerida_no_ejecutada" and p["resolution"]["state"] in {
        "cerrada", "abierta", "pendiente"}
    assert j["scorecard"][0]["vid"] == "ema@1h@v1" and j["in_review"] == []


def test_gap_interval_is_recorded_when_nothing_validated(monkeypatch):
    c, router = make(monkeypatch, [idea()], [verdict(verdict="RECHAZADA")])
    router.tick()
    j = c.get("/v2/setups/history").json()
    assert j["published"] == [] and j["gaps"][0]["status"] == "sin_validadas"
    assert j["gaps"][0]["message"] and j["gap_summary"]["intervals"] == 1
