"""Selector automático (T45) sobre una fotografía real del escáner T38 y gestión de lo abierto."""

from pathlib import Path

import pytest

from eim.arbitrage.common import mid
from eim.core import ArbMarket
from eim.data.arb_store import ArbStore
from eim.execution.arb_book import CLOSED, OPEN
from eim.execution.arb_runner import ArbAutopilot
from tests.execution.arb_helpers import PERP, SPOT, arb_rig

FIXTURE = Path(__file__).parents[1] / "fixtures" / "arbitrage" / "binance_arb_2026-10-15.json"
Q1, Q2 = "BTCUSDT_261225", "BTCUSDT_270326"
H = 3_600_000


def _market() -> ArbMarket:
    return ArbMarket.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def _pilot(tmp_path, mkt: ArbMarket | None = None, directional=()):
    m = mkt or _market()
    mids = {s: mid(b) for s, b in m.futures_books.items() if s in (PERP, Q1, Q2)}
    r = arb_rig(spot_mid=mid(m.spot_books[SPOT]), fut_mid=mids[PERP], qtr_mid=mids[Q1])
    r.fv.mids[Q2] = mids[Q2]
    r.clock.t = m.asof + 1_000
    store = ArbStore(tmp_path)
    if mkt is not False:
        store.save(m)
    pilot = ArbAutopilot(r.ex, r.recon, r.engine, store, lambda k, d: r.journal.append((k, d)),
                         directional_symbols=lambda: directional, clock=r.clock)
    return r, pilot, store


def test_opens_the_best_risk_adjusted_opportunity(tmp_path):
    r, pilot, _ = _pilot(tmp_path)
    rep = pilot.cycle()
    pos = r.ex.positions[rep["opened"]]
    assert pos.strategy == "basis" and pos.fut.symbol == Q2      # mayor puntuación (0,70)
    assert pos.status == OPEN and r.net(Q2) == 0
    assert pos.approved_qty <= 1000.0 / mid(_market().spot_books[SPOT]) + 1e-12  # tope 1 000 USD
    assert rep["decisions"][0]["approved"] and len(rep["decisions"]) == 1
    rep2 = pilot.cycle(r.clock())                    # base BTC ya abierta → el carry
    assert r.ex.positions[rep2["opened"]].strategy == "funding_carry"
    rep3 = pilot.cycle(r.clock())
    assert rep3["opened"] is None and "ninguna" in rep3["skipped"]
    kinds = [k for k, _ in r.journal]
    assert "ciclo" in kinds and "apertura" in kinds and len(r.decisions) == 2


def test_risk_veto_moves_to_the_next_candidate(tmp_path):
    r, pilot, _ = _pilot(tmp_path, directional=(Q2,))  # operación direccional en Q2
    rep = pilot.cycle()
    assert [d["approved"] for d in rep["decisions"]] == [False, True]
    assert any("conflicto direccional" in x for x in rep["decisions"][0]["reasons"])
    assert r.ex.positions[rep["opened"]].fut.symbol == Q1


def test_stale_scan_opens_nothing(tmp_path):
    r, pilot, _ = _pilot(tmp_path)
    r.clock.t += 120_000
    rep = pilot.cycle()
    assert rep["opened"] is None and "vigente" in rep["skipped"] and r.ex.positions == {}


def test_kill_switch_stops_the_cycle_and_flattens(tmp_path):
    r, pilot, _ = _pilot(tmp_path)
    pos = r.ex.positions[pilot.cycle()["opened"]]
    r.kill.activate("prueba", r.clock())
    rep = pilot.cycle(r.clock())
    assert pos.status == CLOSED and r.net(Q2) == 0 and rep["opened"] is None


def test_funding_that_turns_negative_closes_the_carry(tmp_path):
    r, pilot, store = _pilot(tmp_path, mkt=False)
    pos = r.open()                                   # carry abierto sobre BTCUSDT
    base = _market()
    for i in range(3):
        prem = base.premium[PERP].model_copy(update={"funding_rate": -5e-5})
        m = base.model_copy(update={"asof": base.asof + (i + 1) * 60_000,
                                    "premium": {**base.premium, PERP: prem}})
        store.save(m)
        r.clock.t = m.asof + 1_000
        pilot.cycle()
        if i < 2:
            assert pos.status == OPEN and pos.negative_funding_streak == i + 1
    assert pos.status == CLOSED and "cambió de signo" in pos.exit_reason
    assert r.net_all() == pytest.approx(0.0, abs=1e-9) and r.short() == 0
    assert "funding_carry:BTC" not in r.ex.open_keys()   # con funding < 0 no se reabre


def _rally(r, pct: float) -> None:
    r.fv.mids[PERP] *= 1 + pct
    r.sv.mids[SPOT] *= 1 + pct


def test_rebalance_adds_free_margin(tmp_path):
    r, pilot, _ = _pilot(tmp_path, mkt=False)
    pos = r.open()
    before = r.fv.pos[PERP][2]
    _rally(r, 0.18)                                  # el corto pierde: margen al ~39 %
    rep = pilot.cycle()
    assert any("rebalanceo" in a for a in rep["actions"])
    assert pos.rebalances == 1 and pos.margin_added > 0
    assert r.fv.pos[PERP][2] == pytest.approx(before + pos.margin_added)
    assert pos.hedged == pytest.approx(0.01) and r.net() == 0


def test_rebalance_without_free_margin_reduces_both_legs(tmp_path):
    r, pilot, _ = _pilot(tmp_path, mkt=False)
    pos = r.open()
    r.fv.wallet = 400.0                              # sin margen libre en futuros
    _rally(r, 0.18)
    pilot.cycle()
    assert pos.rebalances == 1 and pos.margin_added == 0
    assert pos.hedged == pytest.approx(0.004) and r.net() == pytest.approx(0.0, abs=1e-9)


def test_near_liquidation_closes_urgently(tmp_path):
    r, pilot, _ = _pilot(tmp_path, mkt=False)
    pos = r.open()
    _rally(r, 0.26)                                  # liquidación a < 8 %
    pilot.cycle()
    assert pos.status == CLOSED and "liquidación" in pos.exit_reason and r.net() == 0


def test_cycle_horizon_closes_after_holding_period(tmp_path):
    r, pilot, _ = _pilot(tmp_path, mkt=False)
    pos = r.open(horizon_h=24.0)
    r.clock.t += 25 * H
    pilot.cycle()
    assert pos.status == CLOSED and "tenencia" in pos.exit_reason


def test_failed_open_waits_before_retrying_same_key(tmp_path):
    r, pilot, _ = _pilot(tmp_path)
    r.fh.fault("POST", "/fapi/v1/order", "reject", times=50, code=-2019, msg="Margin")
    r.sv.liquidity[SPOT] = 5.0
    first = pilot.cycle()
    assert r.ex.positions[first["opened"]].status == "FALLIDA"
    second = pilot.cycle(r.clock())                          # base BTC en enfriamiento → carry
    assert r.ex.positions[second["opened"]].strategy == "funding_carry"
    third = pilot.cycle(r.clock())
    assert third["opened"] is None                           # ambas claves esperan 1 h


def test_day_start_equity_survives_restart(tmp_path):
    r, pilot, _ = _pilot(tmp_path)
    pilot.cycle()
    day = r.ex.day
    assert day is not None and r.saved[-1]["day"] == day
    r.ex.day = None
    r.ex.load(r.saved[-1])
    assert r.ex.day == day
