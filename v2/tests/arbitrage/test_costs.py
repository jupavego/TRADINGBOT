"""Modelo de costos: comisiones por nivel VIP/BNB y deslizamiento recorriendo el libro."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from eim.arbitrage import ArbParams, scan_funding_carry
from eim.core import CostModel, Costs, Opportunity
from tests.arbitrage.helpers import carry_market


def test_fee_rates_vip_and_bnb():
    cm = CostModel()
    assert cm.fee_rate("spot") == pytest.approx(0.001)
    assert cm.fee_rate("usdm") == pytest.approx(0.0005)
    assert cm.fee_rate("usdm", "maker") == pytest.approx(0.0002)
    bnb = CostModel(bnb_discount=True)
    assert bnb.fee_rate("spot") == pytest.approx(0.00075)  # −25 %
    assert bnb.fee_rate("usdm") == pytest.approx(0.00045)  # −10 %
    assert CostModel(futures_vip=3).fee_rate("usdcm") == pytest.approx(0.00032)
    assert CostModel().settle_rate() == pytest.approx(0.0005)  # conservador: taker
    with pytest.raises(ValidationError):
        CostModel(spot_vip=12)


def test_fill_walks_depth_not_best_price():
    levels = [(100.0, 1.0), (101.0, 1.0), (102.0, 2.0)]
    f = CostModel.fill(levels, base=3.0)
    assert f.complete and f.levels == 3 and f.best == 100.0
    assert f.vwap == pytest.approx(101.0)  # VWAP real, no el mejor precio
    q = CostModel.fill(levels, quote=150.0)
    assert q.quote == pytest.approx(150.0) and q.base == pytest.approx(1 + 50 / 101)
    thin = CostModel.fill(levels, base=10.0)
    assert not thin.complete and thin.base == pytest.approx(4.0)
    assert not CostModel.fill([], base=1.0).complete
    with pytest.raises(ValueError):
        CostModel.fill(levels, base=1.0, quote=1.0)


def test_opportunity_requires_breakdown_and_consistent_net():
    o = scan_funding_carry(carry_market(0.0005, realized=0.0004), CostModel(),
                           ArbParams(assets=("BTC",))).opportunities[0]
    data = o.model_dump()
    data["net_edge"] = o.net_edge + 1.0
    with pytest.raises(ValidationError):
        Opportunity.model_validate(data)  # el neto no cuadra con bruto − costos
    data = o.model_dump()
    data.pop("costs")
    with pytest.raises(ValidationError):
        Opportunity.model_validate(data)  # sin desglose no hay oportunidad
    assert Costs(fees=1, slippage=2, funding=-0.5, borrow=0.25).total == pytest.approx(2.75)
