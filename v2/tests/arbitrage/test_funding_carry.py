"""Carry de funding: esperado vs realizado, cruce de liquidaciones, neto y riesgos."""

from __future__ import annotations

import pytest

from eim.arbitrage import ArbParams, scan_funding_carry, select
from eim.core import CostModel
from tests.arbitrage.helpers import ASOF, H, carry_market, premium

P = ArbParams(assets=("BTC",))
CM = CostModel()


def _direct(mkt, p=P):
    scan = scan_funding_carry(mkt, CM, p)
    return scan, next(o for o in scan.opportunities if o.variant.startswith("largo spot"))


def test_gross_positive_net_negative_with_realistic_fees():
    scan, o = _direct(carry_market(0.0005, realized=0.0004))
    assert scan.status == "ok"
    # próxima en 90 min, 24 h → 3 liquidaciones: prevista + 2 × realizada
    assert o.details["settlements"] == 3
    assert o.gross_edge == pytest.approx((0.0005 + 2 * 0.0004) * 10_000, rel=1e-6)
    assert o.details["gross_if_realized"] == pytest.approx(3 * 0.0004 * 10_000, rel=1e-6)
    # 4 patas: spot 0,10 % ×2 + perpetuo 0,05 % ×2 sobre 10 000
    assert o.costs.fees == pytest.approx(30.0, rel=1e-3)
    assert o.costs.slippage > 0 and o.costs.funding == 0 and o.costs.borrow == 0
    assert o.gross_edge > 0 > o.net_edge
    assert {lg.action for lg in o.legs} == {"open", "close"} and len(o.legs) == 4
    assert select(scan.opportunities, P).rejected[0].reason.startswith("neto")


def test_high_funding_is_selected_with_declared_risk():
    scan, o = _direct(carry_market(0.003, realized=0.003))
    assert o.net_edge > 0 and o.executable
    assert o.capital_required == pytest.approx(10_000 * 1.5, rel=1e-3)  # spot + margen ×2
    assert o.annualized is not None and o.annualized > 0
    assert set(o.risk.notes) == {"legging", "basis", "liquidation", "liquidity"}
    assert 0 < o.risk.liquidation < 1 and o.risk.liquidity < 0.01
    assert o.valid_until == ASOF + P.quote_ttl_s * 1000
    assert o.source == "binance-futures+binance-spot"
    assert "book:spot:BTCUSDT" in o.coverage and "funding:BTCUSDT" in o.coverage
    sel = select(scan.opportunities, P)
    assert [r.opportunity for r in sel.selected] == [o]


def test_predicted_vs_realized_warning():
    _, o = _direct(carry_market(0.0005, realized=0.0001))
    assert any("2× el realizado" in w for w in o.warnings)
    _, o = _direct(carry_market(0.0005, realized=-0.0002))
    assert any("signo contrario" in w for w in o.warnings)


def test_negative_funding_direct_loses_and_reverse_needs_borrow():
    scan, o = _direct(carry_market(-0.0005, realized=-0.0004))
    assert o.gross_edge < 0 and o.net_edge < 0
    assert len(scan.opportunities) == 1
    assert any("carry inverso" in w and "préstamo" in w for w in scan.warnings)
    scan = scan_funding_carry(carry_market(-0.0005, realized=-0.0004, borrow={"BTC": 0.05}),
                              CM, P)
    rev = next(o for o in scan.opportunities if o.variant.startswith("corto spot"))
    assert rev.gross_edge == pytest.approx(13.0, rel=1e-6)
    assert rev.costs.borrow == pytest.approx(10_000 * 0.05 * 24 / 8760, rel=1e-3)
    assert rev.legs[0].side == "sell" and rev.legs[1].side == "buy"


def test_settlement_schedule_crossing():
    _, o = _direct(carry_market(0.001, realized=0.001),
                   ArbParams(assets=("BTC",), carry_horizon_h=1.0))
    assert o.details["settlements"] == 0 and o.gross_edge == 0
    assert any("no cruza ninguna liquidación" in w for w in o.warnings)
    mkt = carry_market(0.001, realized=0.001)
    mkt = mkt.model_copy(update={"premium": {"BTCUSDT": premium(
        "BTCUSDT", 0.001, mark=60_000, next_in_min=90, interval_h=4)}})
    _, o = _direct(mkt)
    assert o.details["settlements"] == 6  # 1,5 h + 4 h × 5 dentro de 24 h


def test_stale_next_funding_rolls_forward():
    mkt = carry_market(0.001, realized=0.001)
    mkt = mkt.model_copy(update={"premium": {"BTCUSDT": premium(
        "BTCUSDT", 0.001, mark=60_000, next_in_min=-30)}})
    _, o = _direct(mkt)
    assert o.details["next_funding_t"] == ASOF - 30 * 60_000 + 8 * H


def test_thin_book_incomplete_leg_not_selected():
    scan, o = _direct(carry_market(0.003, realized=0.003, qty=0.005))
    assert not o.executable and o.risk.legging == 1.0
    assert any("pata incompleta" in w for w in o.warnings)
    assert select(scan.opportunities, P).rejected[0].reason.startswith("pata incompleta")


def test_no_data_without_book_or_funding():
    mkt = carry_market(0.001, realized=0.001)
    scan = scan_funding_carry(mkt.model_copy(update={"premium": {}}), CM, P)
    assert scan.status == "no_data" and not scan.opportunities
    assert any("funding previsto" in m for m in scan.missing)
    no_book = mkt.model_copy(update={"futures_books": {},
                                     "errors": {"book:usdm:BTCUSDT": "HTTP 503"}})
    scan = scan_funding_carry(no_book, CM, P)
    assert scan.status == "no_data" and "HTTP 503" in scan.missing[0]
    scan = scan_funding_carry(mkt.model_copy(update={"contracts": []}), CM, P)
    assert scan.status == "no_data"


def test_missing_realized_history_is_degraded():
    scan, o = _direct(carry_market(0.001))
    assert scan.status == "degraded"
    assert any("sin histórico" in w for w in o.warnings)
    assert o.gross_edge == pytest.approx(3 * 0.001 * 10_000, rel=1e-6)


def test_partial_assets_degraded():
    scan = scan_funding_carry(carry_market(0.001, realized=0.001), CM,
                              ArbParams(assets=("BTC", "ETH")))
    assert scan.status == "degraded" and len(scan.opportunities) == 1
    assert any("ETHUSDT" in m for m in scan.missing)
