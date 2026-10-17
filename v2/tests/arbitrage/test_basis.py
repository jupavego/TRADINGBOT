"""Base / cash-and-carry: spot vs trimestral y perpetuo vs trimestral hasta el vencimiento."""

from __future__ import annotations

import pytest

from eim.arbitrage import ArbParams, scan_basis
from eim.core import CostModel
from tests.arbitrage.helpers import T38, book, history, market, perp, premium, quarterly

P = ArbParams(assets=("BTC",), **T38)
CM = CostModel()


def _mkt(q_mid: float, days: float, *, rate: float = 0.0001, borrow=None, with_q_book=True):
    q = quarterly("BTC", days)
    futures = {"BTCUSDT": book(60_000)}
    if with_q_book:
        futures[q.symbol] = book(q_mid)
    return market(spot={"BTCUSDT": book(60_000)}, futures=futures,
                  prem={"BTCUSDT": premium("BTCUSDT", rate, mark=60_000)},
                  hist={"BTCUSDT": history(rate)}, contracts=[perp("BTC"), q], borrow=borrow)


def _by(scan, prefix):
    return next(o for o in scan.opportunities if o.variant.startswith(prefix))


def test_cash_and_carry_contango_to_expiry():
    scan = scan_basis(_mkt(61_200, 60), CM, P)
    assert scan.status == "ok"
    o = _by(scan, "largo spot")
    qty = 10_000 / 60_000
    assert o.gross_edge == pytest.approx(1_200 * qty, rel=1e-6)
    assert o.horizon_h == pytest.approx(60 * 24)
    # spot 0,10 % entrada + salida, trimestral 0,05 % entrada + liquidación
    assert o.costs.fees == pytest.approx(30.0, rel=5e-3)
    settle = o.legs[-1]
    assert settle.levels == 0 and settle.slippage == 0 and settle.action == "close"
    assert o.net_edge > 0 and o.annualized == pytest.approx(
        o.net_edge / o.capital_required * 365 / 60, rel=1e-6)
    assert o.risk.liquidation > 0.5  # 60 días con ×2: declarado alto
    assert o.details["basis_bps"] == pytest.approx(200, rel=1e-3)


def test_backwardation_needs_borrow():
    scan = scan_basis(_mkt(59_000, 60), CM, P)
    assert not any(o.variant.endswith("largo trimestral") and "spot" in o.variant
                   for o in scan.opportunities)
    assert any("préstamo" in w for w in scan.warnings)
    scan = scan_basis(_mkt(59_000, 60, borrow={"BTC": 0.05}), CM, P)
    o = _by(scan, "corto spot")
    assert o.gross_edge > 0 and o.costs.borrow == pytest.approx(
        10_000 * 0.05 * 60 / 365, rel=1e-3)


def test_perp_vs_quarterly_pays_funding_until_expiry():
    scan = scan_basis(_mkt(60_600, 30, rate=0.0001), CM, P)
    o = _by(scan, "largo perpetuo")
    assert o.details["settlements"] == 90  # 30 días a 8 h
    assert o.costs.funding == pytest.approx(90 * 0.0001 * 10_000, rel=1e-3)  # paga el largo
    assert o.gross_edge == pytest.approx(100.0, rel=1e-6)
    assert o.gross_edge > 0 > o.net_edge
    assert "premium:BTCUSDT" in o.coverage
    # (5 pb de base + 90 liquidaciones × 1 pb) × 10 000 = 95 frente a un bruto de 100
    assert o.risk.basis == pytest.approx(0.95)
    assert "90 liquidaciones" in o.risk.notes["basis"]


def test_negative_funding_is_income_for_the_long_perp():
    o = _by(scan_basis(_mkt(60_600, 30, rate=-0.0001), CM, P), "largo perpetuo")
    assert o.costs.funding < 0  # se cobra
    assert o.net_edge > 0


def test_missing_quarterly_book_is_no_data():
    scan = scan_basis(_mkt(61_000, 60, with_q_book=False), CM, P)
    assert scan.status == "no_data" and "trimestral" in scan.missing[0]
    scan = scan_basis(market(spot={"BTCUSDT": book(60_000)}), CM, P)
    assert scan.status == "no_data"
