"""Rutas /v2/risk: decisión sobre el plan vigente (siempre registrada) y kill-switch."""

import pytest
from fastapi import FastAPI

from eim.api.reports_db import ReportStore
from eim.api.risk import build_risk_router
from eim.core import AgentReport, Candle, Overlay
from eim.data.store import Store
from eim.risk import KillSwitch
from tests.local_client import LocalClient

H = 3_600_000
T0 = 1_700_000_000_000 // H * H
N = 50
LAST_CLOSE = T0 + N * H


def _candles():
    return [Candle(t=T0 + i * H, o=2000.0, h=2010.0, l=1990.0, c=2000.0, v=100.0)
            for i in range(N)]


def _rep(agent, status="ok", **kw):
    return AgentReport(agent_id=agent, version="1", asof=LAST_CLOSE, bias=0, confidence=0,
                       horizon_bars=1, status=status, **kw)


def _plan(status="VIGENTE"):
    geom = {"side": "long", "entry": 2000.0, "sl": 1960.0, "tp": [2080.0], "rr": 2.0,
            "mode": "ANALISIS", "status": status}
    ov = Overlay(id=f"plan:{LAST_CLOSE - H}", agent_id="plan", kind="trade_plan",
                 t_from=LAST_CLOSE - H, geometry=geom, label="Plan", confidence=0.6)
    return _rep("plan", metrics={"plan": geom}, overlays=[ov])


@pytest.fixture
def ctx(tmp_path):
    store = Store(tmp_path)
    store.upsert_candles("ETHUSDT", "1h", _candles(), "test")
    reports = ReportStore(tmp_path / "reports.duckdb")
    clock = {"now": LAST_CLOSE + 60_000}
    ks = KillSwitch()
    app = FastAPI()
    app.include_router(build_risk_router(store, reports, lambda: clock["now"], ks))
    with LocalClient(app) as c:
        yield c, reports, clock, ks
    reports.close()


P = {"symbol": "ETHUSDT", "tf": "1h"}
HDR = {"X-EIM-Confirm": "kill-switch"}


def test_no_plan(ctx):
    c, reports, _, _ = ctx
    reports.save("ETHUSDT", "1h", [_plan("CUMPLIDO")])
    body = c.get("/v2/risk", params=P).json()
    assert body["decision"] is None and body["mode"] == "SIMULADO"
    assert body["config"]["version"] == "risk_v2"


def test_approved_plan_with_size_and_logged(ctx):
    c, reports, _, _ = ctx
    reports.save("ETHUSDT", "1h", [_plan(), _rep("structure"), _rep("levels")])
    body = c.get("/v2/risk", params=P).json()
    d = body["decision"]
    assert d["approved"] and d["size"] > 0 and "seal" not in d
    assert d["risk_amount"] == pytest.approx(10_000 * 0.005)
    assert d["mode"] == "SIMULADO" and "SIMULADO" in body["account"]["source"]
    logged = c.get("/v2/risk/decisions", params=P).json()["decisions"]
    assert len(logged) == 1 and logged[0]["approved"]
    c.get("/v2/risk", params=P)                    # mismo resultado: no duplica
    assert len(c.get("/v2/risk/decisions", params=P).json()["decisions"]) == 1


def test_changed_outcome_kept_in_journal(ctx):
    c, reports, _, ks = ctx
    reports.save("ETHUSDT", "1h", [_plan(), _rep("structure"), _rep("levels")])
    c.get("/v2/risk", params=P)
    ks.activate("prueba", LAST_CLOSE)
    c.get("/v2/risk", params=P)
    rows = c.get("/v2/risk/decisions", params=P).json()["decisions"]
    assert sorted(r["approved"] for r in rows) == [False, True]


def test_old_plan_vetoed_even_with_fresh_candles(ctx, tmp_path):
    c, reports, clock, _ = ctx
    reports.save("ETHUSDT", "1h", [_plan(), _rep("structure"), _rep("levels")])
    more = [Candle(t=LAST_CLOSE + i * H, o=2000.0, h=2010.0, l=1990.0, c=2000.0, v=100.0)
            for i in range(5)]
    Store(tmp_path).upsert_candles("ETHUSDT", "1h", more, "test")   # el agente plan se detuvo
    clock["now"] = LAST_CLOSE + 5 * H + 60_000
    d = c.get("/v2/risk", params=P).json()["decision"]
    assert not d["approved"] and any(r.startswith("vigencia: plan de hace") for r in d["reasons"])


def test_stale_data_vetoed(ctx):
    c, reports, clock, _ = ctx
    reports.save("ETHUSDT", "1h", [_plan(), _rep("structure"), _rep("levels")])
    clock["now"] = LAST_CLOSE + 5 * H
    d = c.get("/v2/risk", params=P).json()["decision"]
    assert not d["approved"] and d["size"] == 0
    assert any("obsoletos" in r for r in d["reasons"])


def test_degraded_critical_agent_vetoed(ctx):
    c, reports, _, _ = ctx
    reports.save("ETHUSDT", "1h", [_plan(), _rep("structure"), _rep("levels", "degraded")])
    d = c.get("/v2/risk", params=P).json()["decision"]
    assert not d["approved"] and any("levels" in r for r in d["reasons"])


def test_kill_switch_endpoints(ctx):
    c, reports, _, ks = ctx
    reports.save("ETHUSDT", "1h", [_plan(), _rep("structure"), _rep("levels")])
    assert c.post("/v2/risk/kill-switch/activate").status_code == 403    # sin cabecera: CSRF
    assert not ks.active
    st = c.post("/v2/risk/kill-switch/activate", params={"reason": "prueba"}, headers=HDR).json()
    assert st["active"] and st["reason"] == "prueba" and ks.active
    d = c.get("/v2/risk", params=P).json()["decision"]
    assert not d["approved"] and d["reasons"][0].startswith("kill-switch")
    assert c.post("/v2/risk/kill-switch/deactivate").status_code == 403
    assert not c.post("/v2/risk/kill-switch/deactivate", headers=HDR).json()["active"]
    assert c.get("/v2/risk", params=P).json()["decision"]["approved"]


def test_bad_symbol(ctx):
    c, _, _, _ = ctx
    assert c.get("/v2/risk", params={"symbol": "XXX", "tf": "1h"}).status_code == 400
