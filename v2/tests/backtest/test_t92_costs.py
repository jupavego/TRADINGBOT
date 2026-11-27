"""T92: modelos de costos por clase — tipo de contrato, fuentes, fórmulas y tamaño."""
from __future__ import annotations

import datetime as dt

import pytest

from eim.backtest.costs import (
    BinanceQuarterlyCostModel,
    ContractKind,
    EquityCostModel,
    FuturesCostModel,
    FxCostModel,
    NotTradable,
    PerpCostModel,
    contract_kind,
    cost_model_for,
)
from eim.backtest.costs.base import Sourced
from eim.backtest.costs.fx import rollovers
from eim.backtest.costs.sizing import class_quantity, quote_to_account
from eim.backtest.params import CostParams
from eim.core import Candle
from eim.instruments.models import AssetClass, make_id
from eim.instruments.registry import BTCUSDT, ETHUSDT, NASDAQ, SP500, XAUUSDT
from tests.backtest.t92_helpers import equity, future, fx

MODELS = [PerpCostModel(), EquityCostModel(), FxCostModel(), FuturesCostModel(),
          BinanceQuarterlyCostModel()]


def _ms(y, m, d, h=0):
    return int(dt.datetime(y, m, d, h, tzinfo=dt.UTC).timestamp() * 1000)


# --- tipo de contrato -------------------------------------------------------
def test_contract_kind_follows_the_contract_not_the_underlying():
    assert contract_kind(BTCUSDT) is ContractKind.PERPETUAL
    assert contract_kind(ETHUSDT) is ContractKind.PERPETUAL
    assert contract_kind(XAUUSDT) is ContractKind.PERPETUAL    # oro, pero perpetuo de Binance
    assert contract_kind(equity()) is ContractKind.EQUITY
    assert contract_kind(fx()) is ContractKind.FX
    assert contract_kind(future()) is ContractKind.FUTURE
    quarterly = BTCUSDT.model_copy(update={"id": make_id(AssetClass.CRYPTO, "binance",
                                                         "BTCUSDT_260327", "usdm"),
                                           "symbol": "BTCUSDT_260327", "expiry": _ms(2026, 3, 27)})
    assert contract_kind(quarterly) is ContractKind.FUTURE
    assert isinstance(cost_model_for(quarterly), BinanceQuarterlyCostModel)


@pytest.mark.parametrize("inst", [SP500, NASDAQ])
def test_index_is_not_tradable(inst):
    with pytest.raises(NotTradable, match="índice"):
        contract_kind(inst)


def test_btc_eth_get_exactly_the_old_cost_params():
    for inst in (BTCUSDT, ETHUSDT):
        m = cost_model_for(inst)
        assert isinstance(m, PerpCostModel) and m.uses_perp_engine
        assert m.params == CostParams()


# --- fuentes y versión -------------------------------------------------------
@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.version)
def test_every_parameter_has_a_source_or_is_marked_assumption(model: Sourced):
    fields = set(type(model).model_fields)
    missing = fields - set(type(model).SOURCES)
    assert not missing, f"{model.version}: sin fuente {missing}"
    assert all(v.strip() for v in type(model).SOURCES.values())
    assert model.version.endswith("_v1")
    assert len(model.fingerprint()) == 16


def test_slippage_params_also_carry_sources():
    sp = EquityCostModel().slippage
    assert set(type(sp).model_fields) <= set(type(sp).SOURCES)
    assert "slippage.spread_bps" in EquityCostModel().assumptions()


def test_models_are_frozen_and_versioned():
    m = EquityCostModel()
    with pytest.raises(Exception):  # noqa: B017 — pydantic frozen
        m.commission_min = 0.0
    assert EquityCostModel(commission_min=2.0).fingerprint() != m.fingerprint()


# --- fórmulas ----------------------------------------------------------------
def test_equity_commission_min_and_cap():
    m = EquityCostModel()
    assert m.commission(10, 50.0) == pytest.approx(1.0)            # mínimo por orden
    assert m.commission(1000, 50.0) == pytest.approx(5.0)          # 0,005 × 1000
    assert m.commission(1000, 0.10) == pytest.approx(1.0)          # tope 1 % de 100 USD
    assert m.commission(0, 50.0) == 0.0


def test_equity_borrow_only_for_shorts_and_dividend_sides():
    m = EquityCostModel(borrow_rate_annual=0.036)
    assert m.financing(1, 10_000, 0, 10 * 86_400_000) == 0.0
    assert m.financing(-1, 10_000, 0, 10 * 86_400_000) == pytest.approx(10_000 * 0.036 * 10 / 360)
    assert m.dividend_cash(1, 100, 0.5) == pytest.approx(50.0)
    assert m.dividend_cash(-1, 100, 0.5) == pytest.approx(-50.0)
    assert EquityCostModel(dividend_withholding=0.15).dividend_cash(1, 100, 0.5) == \
        pytest.approx(42.5)


def test_equity_has_no_implicit_leverage():
    m = EquityCostModel()
    assert m.max_leverage == 1.0
    assert m.margin(1, 10_000).initial == 10_000 and m.margin(1, 10_000).maintenance == 0.0
    assert m.margin(-1, 10_000) == (10_000, 3_000)


def test_fx_spread_by_session_and_leverage_by_regulation():
    m = FxCostModel()
    c = Candle(t=_ms(2026, 1, 6, 13), o=1.1, h=1.1, l=1.1, c=1.1, v=0)     # solape: rango 0
    assert m.session_of(_ms(2026, 1, 6, 13)) == "overlap"
    assert m.session_of(_ms(2026, 1, 6, 21)) == "rollover"
    assert m.session_of(_ms(2026, 1, 6, 3)) == "asia"
    assert m.slippage_frac(c, 1.0) == pytest.approx(0.25e-4, rel=1e-3)   # medio de 0,5 pb
    c_roll = c.model_copy(update={"t": _ms(2026, 1, 6, 21)})
    assert m.slippage_frac(c_roll, 1.0) > m.slippage_frac(c, 1.0)
    assert FxCostModel(pair="EURUSD").max_leverage == 30.0
    assert FxCostModel(pair="EURTRY").max_leverage == 20.0
    assert FxCostModel(pair="EURUSD", regulation="nfa").max_leverage == 50.0
    assert FxCostModel().margin(1, 30_000) == (1_000, 500)


def test_fx_rollover_wednesday_triple_and_weekend_not_double_counted():
    mon = _ms(2026, 1, 5)                    # lunes
    rs = rollovers(mon, mon + 7 * 86_400_000)
    assert [n for _, n in rs] == [1, 1, 3, 1, 1]       # lun, mar, mié ×3, jue, vie
    assert rollovers(_ms(2026, 1, 10), _ms(2026, 1, 11, 23)) == []    # fin de semana: ninguno
    # 17:00 de Nueva York: 22 UTC en invierno, 21 UTC en verano
    assert dt.datetime.fromtimestamp(rs[0][0] / 1000, dt.UTC).hour == 22
    summer = rollovers(_ms(2026, 7, 6), _ms(2026, 7, 7))
    assert dt.datetime.fromtimestamp(summer[0][0] / 1000, dt.UTC).hour == 21


def test_fx_swap_sign_follows_the_rate_differential():
    m = FxCostModel(rate_base_annual=0.02, rate_quote_annual=0.045, swap_markup_annual=0.0)
    wk = (_ms(2026, 1, 5), _ms(2026, 1, 12))           # 7 días de swap (mié ×3)
    assert m.financing(1, 100_000, *wk) == pytest.approx(100_000 * 0.025 * 7 / 365)
    assert m.financing(-1, 100_000, *wk) == pytest.approx(-100_000 * 0.025 * 7 / 365)


def test_futures_commission_margin_and_tick_spread():
    m = FuturesCostModel(initial_margin_per_contract=6_000, maintenance_margin_per_contract=5_500)
    assert m.commission(3, 70.0, 1000) == pytest.approx(6.75)
    assert m.margin(1, 210_000, 3) == (18_000, 16_500)
    assert FuturesCostModel().margin(1, 100_000) == pytest.approx((10_000, 9_000))
    c = Candle(t=0, o=70.0, h=70.0, l=70.0, c=70.0, v=1e9)
    assert m.slippage_frac(c, 1.0, 1e12, tick=0.01) == pytest.approx(0.5 * 0.01 / 70.0, rel=1e-3)
    with pytest.raises(ValueError):
        FuturesCostModel(maintenance_margin_frac=0.2)
    assert BinanceQuarterlyCostModel().commission(2, 100.0) == pytest.approx(2 * 100 * 0.0005)


# --- tamaño -----------------------------------------------------------------
def test_sizing_futures_whole_contracts_with_multiplier():
    m, inst = FuturesCostModel(), future(multiplier=1000)
    q = class_quantity(m, inst, 1, 70.0, 69.0, 100_000, 0.01, 1.0)
    assert q.qty == 1.0 and q.risk_amount == pytest.approx(1000)    # 1 USD × 1000 por contrato
    assert isinstance(class_quantity(m, inst, 1, 70.0, 68.0, 100_000, 0.01, 1.0), str)


def test_sizing_equity_lots_shorts_and_cap():
    m = EquityCostModel()
    q = class_quantity(m, equity(lot=1), 1, 50.0, 49.0, 10_000, 0.01, 1.0)
    assert q.qty == 100 and q.notional == pytest.approx(5_000)
    capped = class_quantity(m, equity(), 1, 50.0, 49.9, 10_000, 0.01, 1.0)
    assert capped.qty == 200 and capped.notes                 # 1× de capital: 10 000 / 50
    no_borrow = EquityCostModel(shortable=False)
    assert "préstamo" in class_quantity(no_borrow, equity(), -1, 50, 51, 10_000, 0.01, 1.0)


def test_currency_conversion_to_account():
    assert quote_to_account(fx("EURUSD"), "USD")(0, 1.1) == 1.0
    assert quote_to_account(fx("USDJPY"), "USD")(0, 150.0) == pytest.approx(1 / 150)
    with pytest.raises(ValueError, match="serie"):
        quote_to_account(fx("EURGBP"), "USD")
    m = FxCostModel(pair="USDJPY")
    rate = quote_to_account(fx("USDJPY"), "USD")(0, 150.0)
    q = class_quantity(m, fx("USDJPY"), 1, 150.0, 149.0, 10_000, 0.01, rate)
    assert q.risk_amount == pytest.approx(100.0, rel=1e-9)    # 1 % de la cuenta, en USD
