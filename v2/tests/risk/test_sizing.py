"""Tamaño por riesgo fijo, tope de apalancamiento y distancia a liquidación."""

import pytest

from eim.backtest.perp import liquidation_price
from eim.risk.sizing import Sizing, max_safe_leverage, size_position
from tests.risk.helpers import CFG


@pytest.mark.parametrize("side,sl", [(1, 98_000.0), (-1, 102_000.0)])
def test_fixed_risk_both_sides(side, sl):
    s = size_position(side, 100_000.0, sl, 10_000.0, CFG)
    assert isinstance(s, Sizing)
    # 0.5 % de 10 000 = 50 USDT hasta el SL; SL a 2 % → nocional 2 500
    assert s.risk_amount == pytest.approx(50.0)
    assert s.notional == pytest.approx(2_500.0)
    assert s.size == pytest.approx(0.025)
    assert 1 <= s.leverage <= CFG.max_leverage and s.leverage == int(s.leverage)
    assert s.margin == pytest.approx(s.notional / s.leverage)
    assert s.liquidation_price == pytest.approx(
        liquidation_price(side, 100_000.0, s.leverage, CFG.mmr))
    # la liquidación queda claramente más allá del SL
    assert (sl - s.liquidation_price) * side > 0
    assert abs(100_000 - s.liquidation_price) >= CFG.min_liq_sl_ratio * 2_000 - 1e-6


def test_tight_sl_capped_by_notional_and_leverage():
    s = size_position(1, 100_000.0, 99_900.0, 10_000.0, CFG)   # SL a 0.1 %
    assert isinstance(s, Sizing)
    assert s.notional <= 10_000 * min(CFG.max_notional_frac, CFG.max_leverage) + 1e-6
    assert s.margin <= 10_000 + 1e-6
    assert s.risk_amount < 50.0 and s.notes and "recortado" in s.notes[0]


def test_wide_sl_lowers_leverage():
    cfg = CFG.model_copy(update={"max_leverage": 20.0})
    lev_tight, lev_wide = max_safe_leverage(0.01, cfg), max_safe_leverage(0.08, cfg)
    assert lev_tight == 20.0
    assert lev_wide == 6.0          # 1 / (2·0.08 + 0.005) = 6.06
    assert 1 / lev_wide - cfg.mmr >= cfg.min_liq_sl_ratio * 0.08


def test_leverage_below_one_vetoes():
    cfg = CFG.model_copy(update={"min_liq_sl_ratio": 30.0})
    out = size_position(1, 100.0, 96.0, 10_000.0, cfg)
    assert isinstance(out, str) and "apalancamiento" in out


def test_risk_never_exceeds_budget():
    for sl in (99_500.0, 99_000.0, 97_000.0, 93_000.0):
        s = size_position(1, 100_000.0, sl, 7_321.0, CFG)
        assert isinstance(s, Sizing)
        assert s.risk_amount <= 7_321.0 * CFG.risk_per_trade + 1e-6
