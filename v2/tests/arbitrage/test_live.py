"""Arbitraje en vivo, parte pura (T45): planes desde el motor T38 y reglas de gestión."""

from pathlib import Path

import pytest

from eim.arbitrage import DEFAULT_PARAMS, select
from eim.arbitrage.live.manage import PositionView, decide, margin_ratio, settlements_between
from eim.arbitrage.live.plan import candidates, plan_of
from eim.arbitrage.scan import STRATEGIES
from eim.core import ArbMarket, CostModel
from eim.risk.arb_config import load_arb_config

FIXTURE = Path(__file__).parents[1] / "fixtures" / "arbitrage" / "binance_arb_2026-10-15.json"
CFG = load_arb_config()
H = 3_600_000


@pytest.fixture(scope="module")
def mkt() -> ArbMarket:
    return ArbMarket.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def _sel(mkt):
    opps = [o for fn in STRATEGIES for o in fn(mkt, CostModel(), DEFAULT_PARAMS).opportunities]
    return select(opps, DEFAULT_PARAMS, mkt.asof)


def test_candidates_follow_selector_score_and_skip_open_keys(mkt):
    sel = _sel(mkt)
    plans = candidates(sel, mkt, CFG.strategies, set(), 3)
    assert [p.strategy for p in plans] == ["basis", "basis", "funding_carry"]
    assert [p.score for p in plans] == sorted((p.score for p in plans), reverse=True)
    assert all(sorted(lg.market for lg in p.legs) == ["spot", "usdm"] for p in plans)
    only = candidates(sel, mkt, CFG.strategies, {"basis:BTC"}, 3)
    assert [p.strategy for p in only] == ["funding_carry"]
    assert candidates(sel, mkt, ("funding_carry",), {"funding_carry:BTC"}, 3) == []


def test_plan_orders_less_liquid_leg_first_and_carries_economics(mkt):
    sel = _sel(mkt)
    carry = next(r for r in sel.selected if r.opportunity.strategy == "funding_carry")
    p = plan_of(carry.opportunity, carry.score, mkt, 3)
    assert p.legs[0].depth_frac >= p.legs[1].depth_frac
    assert p.legs[0].market == "usdm"                     # el perpetuo consume más del libro
    assert p.funding_rate and p.funding_rate > 0 and p.interval_h == 8.0
    assert p.notional == pytest.approx(DEFAULT_PARAMS.notional_usd, rel=1e-6)
    assert p.exit_cost_bps > 0 and p.valid_until > p.asof


def test_carry_with_negative_predicted_funding_is_not_opened(mkt):
    prem = mkt.premium["BTCUSDT"].model_copy(update={"funding_rate": -1e-4})
    neg = mkt.model_copy(update={"premium": {**mkt.premium, "BTCUSDT": prem}})
    assert all(p.strategy != "funding_carry"
               for p in candidates(_sel(mkt), neg, CFG.strategies, set(), 3))


def _view(**kw) -> PositionView:
    base = dict(strategy="funding_carry", opened_at=0, horizon_h=2160.0, qty=0.01, leverage=3,
                mark=100_000.0, margin_equity=333.0, liq_move=0.33)
    base.update(kw)
    return PositionView(**base)


def test_decide_rules_in_order():
    assert decide(_view(), CFG, H).kind == "hold"
    k = decide(_view(kill_active=True), CFG, H)
    assert k.kind == "close" and k.urgent
    liq = decide(_view(liq_move=0.05), CFG, H)
    assert liq.kind == "close" and liq.urgent and "liquidación" in liq.reason
    reb = decide(_view(margin_equity=150.0), CFG, H)
    assert reb.kind == "rebalance" and reb.frac == pytest.approx(1 - 150 / (1000 / 3))
    assert reb.margin_needed == pytest.approx(1000 / 3 - 150)
    assert decide(_view(horizon_h=1.0), CFG, 2 * H).reason.startswith("tenencia")
    neg = decide(_view(negative_funding_streak=CFG.negative_funding_n), CFG, H)
    assert neg.kind == "close" and "signo" in neg.reason and not neg.urgent
    exp = decide(_view(strategy="basis", delivery_t=H + CFG.exit_before_delivery_ms), CFG, H)
    assert exp.kind == "close" and "vencimiento" in exp.reason
    conv = decide(_view(strategy="basis", delivery_t=1000 * H, basis_bps=3.0,
                        exit_cost_bps=15.0), CFG, H)
    assert conv.kind == "close" and "agotada" in conv.reason


def test_margin_ratio_and_settlements():
    assert margin_ratio(_view(margin_equity=1000 / 3)) == pytest.approx(1.0)
    assert margin_ratio(_view(mark=None)) is None
    assert settlements_between(0, 8 * H, 8.0) == 1
    assert settlements_between(1, 8 * H - 1, 8.0) == 0
    assert settlements_between(7 * H, 25 * H, 8.0) == 3
