"""Perpetuos USDT-M vs USDC-M, selector y escaneo completo."""

from __future__ import annotations

import pytest

from eim.arbitrage import ArbParams, scan_all, scan_related_perps, select
from eim.arbitrage.selector import score
from eim.core import CostModel, SpotPair
from tests.arbitrage.helpers import (
    ASOF,
    book,
    carry_market,
    history,
    market,
    perp,
    premium,
    quarterly,
)

P = ArbParams(assets=("BTC",))
CM = CostModel()


def related(usdc_px: float, *, conv: float | None = 0.9998, rate_t=0.0001, rate_c=0.0003):
    spot = {"USDCUSDT": book(conv, step_bps=0.1)} if conv else {}
    return market(
        spot=spot, pairs=[SpotPair(symbol="USDCUSDT", base="USDC", quote="USDT")],
        futures={"BTCUSDT": book(60_000), "BTCUSDC": book(usdc_px)},
        prem={"BTCUSDT": premium("BTCUSDT", rate_t, mark=60_000),
              "BTCUSDC": premium("BTCUSDC", rate_c, mark=usdc_px)},
        hist={"BTCUSDT": history(rate_t), "BTCUSDC": history(rate_c)},
        contracts=[perp("BTC"), perp("BTC", "USDC")])


def test_related_perps_spread_in_usdt_and_funding_per_leg():
    scan = scan_related_perps(related(60_030), CM, P)
    assert scan.status == "ok"
    o = scan.opportunities[0]
    c_usd = 60_030 * 0.9998
    assert o.details["spread_bps"] == pytest.approx((c_usd - 60_000) / 60_000 * 1e4, rel=1e-6)
    assert o.variant == "largo USDT-M / corto USDC-M"
    assert {lg.market for lg in o.legs} == {"usdm", "usdcm"}
    # largo USDT-M paga 3×0,01 %; corto USDC-M cobra 3×0,03 % → neto se cobra
    assert o.costs.funding < 0
    assert o.risk.basis >= 0.5  # sin convergencia forzada
    assert "book:spot:USDCUSDT" in o.coverage


def test_related_perps_no_data_without_conversion():
    scan = scan_related_perps(related(60_030, conv=None), CM, P)
    assert scan.status == "no_data" and "USDCUSDT" in scan.missing[0]


def test_selector_orders_by_risk_adjusted_return():
    lo = scan_all(carry_market(0.002, realized=0.002), CM, P)
    hi = scan_all(carry_market(0.004, realized=0.004), CM, P)
    opps = [r.opportunity for r in lo.selection.selected + hi.selection.selected]
    assert len(opps) == 2
    sel = select(opps, P)
    assert sel.selected[0].opportunity.gross_edge > sel.selected[1].opportunity.gross_edge
    assert sel.selected[0].score == pytest.approx(score(sel.selected[0].opportunity, P))


def test_selector_rejects_with_reasons():
    o = scan_all(carry_market(0.003, realized=0.003), CM, P).selection.selected[0].opportunity
    strict = ArbParams(assets=("BTC",), min_net_bps=1_000)
    assert select([o], strict).rejected[0].reason.startswith("neto")
    thin = ArbParams(assets=("BTC",), max_liquidity_risk=0.0001)
    assert select([o], thin).rejected[0].reason.startswith("liquidez insuficiente")
    assert select([o], P, now=ASOF + 60_000).rejected[0].reason == "precio caducado"


def test_scan_all_every_opportunity_has_breakdown():
    q = quarterly("BTC", 45)
    mkt = market(spot={"BTCUSDT": book(60_000), "USDCUSDT": book(1.0, step_bps=0.1)},
                 futures={"BTCUSDT": book(60_030), q.symbol: book(61_000),
                          "BTCUSDC": book(60_010)},
                 prem={"BTCUSDT": premium("BTCUSDT", 0.0002, mark=60_030, index=60_000),
                       "BTCUSDC": premium("BTCUSDC", 0.0001, mark=60_010, index=60_000)},
                 hist={"BTCUSDT": history(0.0002), "BTCUSDC": history(0.0001)},
                 contracts=[perp("BTC"), perp("BTC", "USDC"), q])
    res = scan_all(mkt, CM, P)
    strategies = {s.strategy: s.status for s in res.scans}
    assert strategies["funding_carry"] == "ok" and strategies["basis"] == "ok"
    assert strategies["related_perps"] == "ok"
    assert strategies["triangular"] == "ok"  # sin pares cruzados: nada que valorar
    every = [r.opportunity for r in res.selection.selected + res.selection.rejected]
    assert len(every) == sum(len(s.opportunities) for s in res.scans) >= 4
    for o in every:
        assert o.costs.fees > 0 and o.net_edge == pytest.approx(o.gross_edge - o.costs.total)
        assert o.source and o.coverage
