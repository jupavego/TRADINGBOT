"""Ruta `/v2/operation`: estado, posición, P&L, riesgo usado, vetos, alertas e informe."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from eim.api.operation import build_operation_router
from eim.api.risk import build_risk_router
from eim.operation import alerts as A
from tests.operation.helpers import SYM, Market, Rig


@pytest.fixture
def ctx(tmp_path):
    rig = Rig(tmp_path, Market())
    op = rig.build()
    app = FastAPI()
    app.include_router(build_risk_router(op.desk.store, rig.reports, desk=op.desk))
    app.include_router(build_operation_router(op.desk, lambda: rig.op, rig.root / "out",
                                              rig.now))
    with TestClient(app) as c:
        yield c, rig
    rig.close()


def test_overview_with_open_position(ctx):
    c, rig = ctx
    rig.op.step()
    body = c.get("/v2/operation").json()
    assert body["mode"] == "SIMULADO" and body["execution_enabled"]
    assert body["service"]["mode"] == "SIMULADO"
    (p,) = body["positions"]
    assert p["symbol"] == SYM and p["side"] == 1 and p["last"] == 2000.0
    assert p["risk"] == pytest.approx(50.0, rel=0.05)                # 0.5 % de 10 000
    assert body["pnl"]["equity"] == pytest.approx(10_000, rel=1e-3)
    r = body["risk"]
    assert r["open_trades"]["value"] == 1 and r["open_trades"]["limit"] == 2
    assert r["open_risk"]["value"] == pytest.approx(0.005, rel=0.05)
    assert body["kill_switch"]["active"] is False and body["reconciliation"]["ok"]


def test_vetoes_and_alerts_listed(ctx):
    c, rig = ctx
    rig.op.step()
    rig.advance(3_600_000)
    rig.market.down = False
    rig.op.step()                         # 2.º plan: vetado (ya hay una posición abierta)
    rig.op.alerts.emit(A.Alert(rig.now(), A.DRAWDOWN, A.WARN, "Drawdown 6 %"))
    body = c.get("/v2/operation").json()
    assert body["vetoed"] and any("abiertas" in x or "símbolo" in x
                                  for x in body["vetoed"][0]["reasons"])
    assert body["alerts"][0]["kind"] == A.DRAWDOWN


def test_kill_switch_button_route_shared(ctx):
    c, rig = ctx
    r = c.post("/v2/risk/kill-switch/activate", params={"reason": "panel"},
               headers={"X-EIM-Confirm": "kill-switch"})
    assert r.status_code == 200
    assert c.get("/v2/operation").json()["kill_switch"]["active"] and rig.kill.active


def test_report_requires_header_and_is_readable(ctx):
    c, rig = ctx
    rig.op.step()
    assert c.post("/v2/operation/report").status_code == 403
    out = c.post("/v2/operation/report", headers={"X-EIM-Confirm": "report"}).json()
    name = out["md"].replace("\\", "/").rsplit("/", 1)[-1]
    md = c.get("/v2/operation/report", params={"name": name}).json()["markdown"]
    assert md.startswith("# Informe de operación")
    assert c.get("/v2/operation/report", params={"name": "../x.md"}).status_code == 422
    assert name in c.get("/v2/operation").json()["reports"]


def test_without_service(tmp_path):
    rig = Rig(tmp_path, Market())
    op = rig.build()
    app = FastAPI()
    app.include_router(build_operation_router(op.desk, lambda: None, tmp_path / "out"))
    with TestClient(app) as c:
        body = c.get("/v2/operation").json()
        assert body["service"] is None and body["alerts"] == []
        assert c.post("/v2/operation/report",
                      headers={"X-EIM-Confirm": "report"}).status_code == 409
    rig.close()
