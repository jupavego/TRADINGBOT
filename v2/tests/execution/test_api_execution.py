"""Rutas de ejecución: modo TESTNET, envío solo por `/v2/risk/execute`, reconciliación y cierre."""

import pytest
from fastapi import FastAPI

from eim.api.execution import build_execution_router, build_runtime
from eim.api.reports_db import ReportStore
from eim.api.risk import build_risk_router
from eim.data.store import Store
from eim.execution.binance_testnet import ENV_KEY, BinanceTestnetBroker, Credentials
from eim.risk import KillSwitch
from tests.execution.fake_binance import KEY, SECRET, FakeBinance
from tests.local_client import LocalClient
from tests.risk.helpers import CFG
from tests.risk.test_api_risk import LAST_CLOSE, P, _candles, _plan, _rep

EXEC = {"X-EIM-Confirm": "execution"}
GO = {"X-EIM-Confirm": "execute"}


def _app(tmp_path, kind="testnet"):
    store = Store(tmp_path)
    store.upsert_candles("ETHUSDT", "1h", _candles(), "test")
    reports = ReportStore(tmp_path / "reports.duckdb")
    reports.save("ETHUSDT", "1h", [_plan(), _rep("structure"), _rep("levels")])
    fx = FakeBinance()
    fx.sim.set_price("ETHUSDT", 2000.0)
    ks = KillSwitch()
    rt = build_runtime(kind, ks, CFG, lambda: BinanceTestnetBroker(
        Credentials(KEY, SECRET), client=fx.client()))
    now = lambda: LAST_CLOSE + 60_000  # noqa: E731
    app = FastAPI()
    app.include_router(build_risk_router(store, reports, now, ks, rt))
    app.include_router(build_execution_router(rt, now))
    return app, fx, reports


@pytest.fixture
def ctx(tmp_path):
    app, fx, reports = _app(tmp_path)
    with LocalClient(app) as c:
        yield c, fx
    reports.close()


def test_mode_is_testnet_and_account_from_exchange(ctx):
    c, _ = ctx
    body = c.get("/v2/risk", params=P).json()
    assert body["mode"] == "TESTNET" and body["decision"]["mode"] == "TESTNET"
    assert body["account"]["source"].startswith("TESTNET") and body["account"]["equity"] == 10_000
    assert c.get("/v2/execution").json()["mode"] == "TESTNET"


def test_execute_requires_header_then_opens_protected(ctx):
    c, fx = ctx
    assert c.post("/v2/risk/execute", params=P).status_code == 403
    assert fx.posts("/fapi/v1/order") == []
    body = c.post("/v2/risk/execute", params=P, headers=GO).json()
    assert body["executed"] and body["trade"]["status"] == "ABIERTA"
    assert fx.sim.position("ETHUSDT").qty == body["trade"]["qty"] == 1.25
    stops = [o for o in fx.sim.open_orders("ETHUSDT") if o.kind == "STOP"]
    assert stops and stops[0].trigger == 1960.0
    rec = c.post("/v2/execution/reconcile", headers=EXEC).json()
    assert rec["ok"], rec
    st = c.get("/v2/execution").json()
    assert len(st["trades"]) == 1 and st["reconciliation"]["ok"]
    assert c.post("/v2/execution/flatten", params={"symbol": "ETHUSDT"}).status_code == 403
    out = c.post("/v2/execution/flatten", params={"symbol": "ETHUSDT"}, headers=EXEC).json()
    assert out["flat"] and fx.sim.position("ETHUSDT").qty == 0
    assert fx.sim.open_orders("ETHUSDT") == []


def test_execution_off_sends_nothing(tmp_path):
    app, fx, reports = _app(tmp_path, kind="off")
    with LocalClient(app) as c:
        assert c.get("/v2/risk", params=P).json()["mode"] == "SIMULADO"
        assert c.post("/v2/risk/execute", params=P, headers=GO).status_code == 409
        assert c.get("/v2/execution").json()["enabled"] is False
    assert fx.log == []
    reports.close()


def test_testnet_without_keys_stays_simulated(monkeypatch):
    monkeypatch.delenv(ENV_KEY, raising=False)
    rt = build_runtime("testnet", KillSwitch(), CFG)
    assert rt.svc is None and ENV_KEY in rt.error and rt.mode.value == "SIMULADO"
