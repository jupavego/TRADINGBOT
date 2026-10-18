"""Rutas de ejecución de arbitraje (T45): modo TESTNET, cabecera obligatoria, ciclo y estado."""

from pathlib import Path

import pytest
from fastapi import FastAPI

from eim.api.arb_execution import build_arb_execution_router, build_arb_runtime
from eim.arbitrage.common import mid
from eim.core import ArbMarket
from eim.data.arb_store import ArbStore
from eim.execution.arb_legs import ExecParams
from eim.execution.binance_rest import Credentials
from eim.execution.binance_spot_testnet import BinanceSpotTestnetBroker
from eim.execution.binance_testnet import BinanceTestnetBroker
from eim.risk import KillSwitch
from tests.execution.arb_helpers import PERP, SPOT, Clock
from tests.execution.fake_binance import KEY, SECRET
from tests.execution.fake_venue import FakeHTTP, Venue
from tests.local_client import LocalClient

FIXTURE = Path(__file__).parents[1] / "fixtures" / "arbitrage" / "binance_arb_2026-10-15.json"
Q2 = "BTCUSDT_270326"


def _app(tmp_path, kind="testnet"):
    m = ArbMarket.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    sv = Venue({SPOT: mid(m.spot_books[SPOT])}, step=0.00001, tick=0.01)
    fv = Venue({s: mid(m.futures_books[s]) for s in (PERP, "BTCUSDT_261225", Q2)},
               futures=True)
    scans = ArbStore(tmp_path)
    scans.save(m)
    clock = Clock(m.asof + 1_000)
    rt = build_arb_runtime(
        kind, KillSwitch(), tmp_path, scans,
        spot_factory=lambda: BinanceSpotTestnetBroker(Credentials(KEY, SECRET),
                                                      client=FakeHTTP(sv).client(), clock=clock),
        fut_factory=lambda: BinanceTestnetBroker(Credentials(KEY, SECRET),
                                                 client=FakeHTTP(fv).client(), clock=clock),
        exec_params=ExecParams(), clock=clock, sleep=clock.sleep)
    app = FastAPI()
    app.include_router(build_arb_execution_router(rt))
    return LocalClient(app), rt, sv, fv


@pytest.fixture
def ctx(tmp_path):
    return _app(tmp_path)


def test_off_by_default_is_explicit(tmp_path):
    c, rt, *_ = _app(tmp_path, kind="off")
    s = c.get("/v2/arbitrage/execution").json()
    assert s["mode"] == "TESTNET" and s["enabled"] is False and s["positions"] == []
    r = c.post("/v2/arbitrage/execution/cycle", headers={"X-EIM-Confirm": "arb-cycle"})
    assert r.status_code == 409 and "EIM_ARB_EXECUTION" in r.json()["detail"]


def test_unsupported_kind_reports_error(tmp_path):
    _, rt, *_ = _app(tmp_path, kind="real")
    assert rt.pilot is None and "solo testnet" in rt.error


@pytest.mark.parametrize("path", ["cycle", "flatten", "close?key=x"])
def test_posts_require_confirm_header(ctx, path):
    c, *_ = ctx
    assert c.post(f"/v2/arbitrage/execution/{path}").status_code == 403


def test_cycle_opens_and_status_shows_everything(ctx, tmp_path):
    c, rt, sv, fv = ctx
    rep = c.post("/v2/arbitrage/execution/cycle", headers={"X-EIM-Confirm": "arb-cycle"}).json()
    assert rep["opened"] and rep["decisions"][0]["approved"]
    s = c.get("/v2/arbitrage/execution").json()
    assert s["mode"] == "TESTNET" and s["enabled"] and s["config"]["version"] == "risk_arb_v1"
    row = s["positions"][0]
    assert row["status"] == "ABIERTA" and row["futures_symbol"] == Q2
    assert row["spot"] == pytest.approx(-row["futures"]) and row["hedged"] > 0
    kinds = {e["kind"] for e in s["journal"]}
    assert {"ciclo", "riesgo", "apertura"} <= kinds
    assert (tmp_path / "arb_exec" / "state.json").exists()
    # el estado sobrevive a un reinicio: un runtime nuevo lo recarga
    c2, rt2, *_ = _app(tmp_path)
    assert rt2.ex.positions.keys() == rt.ex.positions.keys()
    assert rt2.futures_qty(Q2) == pytest.approx(row["futures"])


def test_close_and_flatten(ctx):
    c, rt, sv, fv = ctx
    key = c.post("/v2/arbitrage/execution/cycle",
                 headers={"X-EIM-Confirm": "arb-cycle"}).json()["opened"]
    assert c.post("/v2/arbitrage/execution/close?key=nada",
                  headers={"X-EIM-Confirm": "arb-close"}).status_code == 404
    r = c.post(f"/v2/arbitrage/execution/close?key={key}",
               headers={"X-EIM-Confirm": "arb-close"}).json()
    assert r["flat"] and r["status"] == "CERRADA" and fv.pos[Q2][0] == 0
    f = c.post("/v2/arbitrage/execution/flatten", headers={"X-EIM-Confirm": "arb-flatten"})
    assert f.json() == {"flat": True}
