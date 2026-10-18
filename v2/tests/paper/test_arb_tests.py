"""Pruebas del arbitraje en el bróker simulado (T45, modo SIMULADO): exchange en memoria,
escenarios sobre una serie sintética (sin red) y API."""

import pytest
from fastapi import FastAPI

from eim.api.paper_arb import build_paper_arb_router
from eim.core import Candle, Mode
from eim.data.arb_sim_data import H_MS, SimSeries, load_sim_series
from eim.data.store import Store
from eim.execution.arb_executor import ArbExecutor
from eim.execution.arb_sim import SimVenue
from eim.execution.arb_sim_brokers import SimFuturesBroker, SimSpotBroker
from eim.execution.broker import LIMIT, MARKET, OrderRejected, OrderSpec
from eim.paper.arb_tests import run_all
from eim.risk import KillSwitch
from tests.execution.arb_helpers import arb_rig
from tests.local_client import LocalClient

T0 = 1_792_000_800_000                     # múltiplo de 8 h
SYM = "BTCUSDT"


def _series(n: int = 60, drift: float = 0.0005, rate: float = 6e-5) -> SimSeries:
    ts = [T0 + i * H_MS for i in range(n)]
    spot = [80_000.0 * (1 + drift) ** i for i in range(n)]
    fut = [p * 1.0004 for p in spot]
    fund = [(t + 3, rate) for t in ts if (t + 3) % (8 * H_MS) == 3 and t > ts[0]]
    return SimSeries(SYM, ts, spot, fut, fund, [rate] * 21,
                     {"spot": "prueba", "futuros": "prueba", "funding": "prueba"})


def test_all_three_scenarios_pass_on_a_quiet_market():
    rep = run_all(_series(), hold_h=48)
    assert rep["mode"] == "SIMULADO" and rep["config"] == "risk_arb_sim_v1"
    assert [s["id"] for s in rep["scenarios"]] == ["carry", "fail", "cut"]
    bad = [(s["id"], c["label"]) for s in rep["scenarios"] for c in s["checks"] if not c["ok"]]
    assert bad == [] and rep["ok"]
    carry = rep["scenarios"][0]
    assert carry["settlements"] == 6 and carry["position"]["funding_n"] == 6
    assert carry["position"]["funding_received"] > 0
    assert carry["fees_usd"] > 0 and len(carry["track"]) == 48
    assert len(rep["series"]["spot"]) == 60


def test_negative_expected_funding_is_vetoed_honestly():
    rep = run_all(_series(rate=-1e-4), hold_h=24)
    carry = rep["scenarios"][0]
    first = carry["checks"][0]
    assert not carry["ok"] and not first["ok"] and "neto" in first["detail"]
    assert not rep["ok"]


def test_rally_that_squeezes_the_short_is_rebalanced_not_liquidated():
    rep = run_all(_series(n=40, drift=0.006), hold_h=32)    # +21 % en 32 h
    carry = rep["scenarios"][0]
    assert carry["position"]["rebalances"] >= 1
    assert "liquidación" not in carry["position"]["exit_reason"]


def test_sim_brokers_fees_minimums_and_liquidation():
    sv, fv = SimVenue(depth={SYM: 3.0}), SimVenue()
    spot, fut = SimSpotBroker(sv), SimFuturesBroker(fv)
    sv.set_mid(SYM, 100_000.0)
    fv.set_mid(SYM, 100_000.0)
    st = spot.post_order(OrderSpec("a", SYM, 1, LIMIT, qty=0.01, price=100_100.0))
    assert st.fee_asset == "BTC" and spot.free("BTC") == pytest.approx(0.00999)
    with pytest.raises(OrderRejected, match="notional"):
        fut.post_order(OrderSpec("b", SYM, -1, MARKET, qty=0.001))
    fut.prepare(SYM, 3)
    fut.post_order(OrderSpec("c", SYM, -1, MARKET, qty=0.01))
    liq = fut.position_risk(SYM)["liq"]
    assert 132_000 < liq < 133_000                           # ×3 aislado, corto
    fv.set_mid(SYM, liq + 1)
    assert fut.position(SYM).qty == 0 and fv.liquidations


def test_executor_requires_same_mode_and_never_real():
    r = arb_rig()
    with pytest.raises(PermissionError, match="TESTNET o SIMULADO"):
        ArbExecutor(SimSpotBroker(SimVenue()), r.fut, KillSwitch())
    assert ArbExecutor(SimSpotBroker(SimVenue()), SimFuturesBroker(SimVenue()),
                       KillSwitch()).mode == Mode.SIMULADO


def _store(tmp_path) -> Store:
    s = _series(n=70)
    st = Store(tmp_path)
    for kind, px in (("spot_candles", s.spot), ("candles", s.fut)):
        st.upsert_candles(SYM, "1h", [Candle(t=t, o=p, h=p, l=p, c=p, v=1.0)
                                      for t, p in zip(s.t, px, strict=True)], "prueba", kind=kind)
    st.upsert_series("funding", SYM, "-", [(T0 - 8 * H_MS * i, 6e-5) for i in range(1, 22)]
                     + s.funding, "prueba")
    return st


def test_loader_aligns_spot_and_perpetual(tmp_path):
    s = load_sim_series(_store(tmp_path), hours=56)
    assert s is not None and len(s.t) == 56 and len(s.funding_hist) == 21
    assert load_sim_series(Store(tmp_path / "vacío"), hours=10) is None


def test_api_runs_and_persists(tmp_path):
    app = FastAPI()
    app.include_router(build_paper_arb_router(_store(tmp_path), tmp_path))
    c = LocalClient(app)
    assert c.get("/v2/paper/arbitrage").json() == {"mode": "SIMULADO", "report": None}
    assert c.post("/v2/paper/arbitrage/run").status_code == 403
    r = c.post("/v2/paper/arbitrage/run?hold_h=48", headers={"X-EIM-Confirm": "paper-arb"})
    assert r.status_code == 200 and r.json()["report"]["ok"]
    again = c.get("/v2/paper/arbitrage").json()["report"]
    assert again["generated_at"] and len(again["scenarios"]) == 3
