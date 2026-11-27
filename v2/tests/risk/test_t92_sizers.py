"""T92: un `Sizer` por clase; el perpetuo sigue con `size_position` sin cambiar un decimal."""
from __future__ import annotations

import pytest

from eim.backtest.costs import EquityCostModel, FuturesCostModel, FxCostModel
from eim.instruments.registry import BTCUSDT, ETHUSDT, XAUUSDT
from eim.risk.config import load_config
from eim.risk.sizers import ClassLimits, ClassSizer, ClassSizing, PerpSizer, sizer_for
from eim.risk.sizing import size_position
from tests.backtest.t92_helpers import equity, future, fx

CFG = load_config()


@pytest.mark.parametrize("inst", [BTCUSDT, ETHUSDT, XAUUSDT])
@pytest.mark.parametrize("side,entry,sl", [(1, 60_000.0, 59_100.0), (-1, 3_000.0, 3_060.0),
                                           (1, 100.0, 99.95), (1, 100.0, 70.0)])
def test_perpetual_sizer_is_the_old_function(inst, side, entry, sl):
    s = sizer_for(inst)
    assert isinstance(s, PerpSizer)
    assert s.size(side, entry, sl, 10_000, CFG) == size_position(side, entry, sl, 10_000, CFG)
    assert s.size(side, entry, sl, 10_000, CFG, 0.5, "evento") == \
        size_position(side, entry, sl, 10_000, CFG, scale=0.5, why="evento")


def test_equity_sizer_cash_account_no_leverage():
    s = sizer_for(equity())
    assert isinstance(s, ClassSizer)
    r = s.size(1, 50.0, 48.0, 10_000, CFG)
    assert isinstance(r, ClassSizing)
    assert r.size == float(int(r.size))                     # lote de 1 acción
    assert r.leverage <= 1.0 + 1e-12 and r.margin_call_price is None
    assert r.cost_model == "equity_v1"
    assert "préstamo" in sizer_for(equity(), model=EquityCostModel(shortable=False)).size(
        -1, 50.0, 52.0, 10_000, CFG)


def test_futures_sizer_contracts_margin_and_limits():
    m = FuturesCostModel(initial_margin_per_contract=6_000, maintenance_margin_per_contract=5_500)
    s = sizer_for(future(multiplier=1000), model=m)
    r = s.size(1, 70.0, 69.5, 100_000, CFG)
    assert isinstance(r, ClassSizing) and r.size == float(int(r.size)) >= 1
    assert r.margin == pytest.approx(6_000 * r.size)
    capped = sizer_for(future(multiplier=1000), model=m, limits=ClassLimits(max_contracts=1))
    assert capped.size(1, 70.0, 69.9, 100_000, CFG).size == 1.0
    assert isinstance(sizer_for(future(multiplier=1000), model=m).size(1, 70.0, 60.0, 10_000,
                                                                       CFG), str)


def test_fx_sizer_leverage_by_regulation_and_conversion():
    s = sizer_for(fx("USDJPY"), model=FxCostModel(pair="USDJPY"))
    r = s.size(1, 150.0, 149.0, 10_000, CFG)
    assert isinstance(r, ClassSizing)
    assert r.risk_amount == pytest.approx(10_000 * CFG.risk_per_trade, rel=1e-9)
    assert r.leverage <= min(30.0, CFG.max_notional_frac) + 1e-9
    assert r.margin_call_price is None or r.margin_call_price < 149.0   # lejos: no llega a 0


def test_class_sizer_vetoes_when_margin_call_precedes_stop():
    m = FuturesCostModel(initial_margin_per_contract=1_000, maintenance_margin_per_contract=1_005)
    s = sizer_for(future(multiplier=10), model=m)
    r = s.size(1, 100.0, 98.0, 1_020, CFG.model_copy(update={"risk_per_trade": 0.02}))
    assert isinstance(r, str) and "margen" in r and "antes que el SL" in r
    ok = s.size(1, 100.0, 99.0, 1_020, CFG.model_copy(update={"risk_per_trade": 0.02}))
    assert isinstance(ok, ClassSizing) and ok.margin_call_price == pytest.approx(98.5)
