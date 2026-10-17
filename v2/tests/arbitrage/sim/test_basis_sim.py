"""Base simulada: convergencia por liquidación del trimestral y funding del perpetuo."""

from __future__ import annotations

import pytest

from eim.arbitrage.params import ArbParams
from eim.arbitrage.sim import DepthModel, Funding, SimParams, SimTrade
from eim.arbitrage.sim.hedge import Side_, futures_pair, spot_short
from eim.arbitrage.sim.trade import Executor
from eim.core import CostModel
from tests.arbitrage.helpers import T38
from tests.arbitrage.sim.helpers import FREE, T0, H, flat, funding, profile, quarterly

P = ArbParams(assets=("BTC",), **T38)
D = T0 + 8 * H * 200  # vencimiento en la rejilla de 8 h
HOLD = 720
Q = 0.2


def _tr(strategy: str) -> SimTrade:
    return SimTrade(strategy=strategy, variant="test", asset="BTC", instrument="BTCUSDT_X",
                    entry_t=D - HOLD * H, capital=15_000.0, notional=10_000.0)


def _ex(cm: CostModel, sp: SimParams) -> Executor:
    keys = ("spot:BTCUSDT", "usdm:BTCUSDT", "usdm:BTCUSDT_Q1")
    return Executor(cm, DepthModel([profile(k, ((0.0, 1e12),)) for k in keys]), sp)


def test_cash_and_carry_captures_the_basis_at_settlement():
    sp = SimParams(p_fail=0.0)
    spot = flat(HOLD + 3, 50_000.0, start=D - HOLD * H)
    qt = quarterly("BTCUSDT_X", D, 51_000.0, settle=50_000.0, n_before=HOLD)
    tr = spot_short(_tr("basis"), _ex(CostModel(), sp), sp, P,
                    Side_(spot, "spot:BTCUSDT", "spot"), Side_(qt.bars, "usdm:BTCUSDT_Q1", "usdm"),
                    q=Q, exit_t=D, settle=qt.settle)
    assert tr is not None and tr.exit_reason == "settle" and tr.exit_t == D
    assert tr.price_pnl == pytest.approx(Q * 1_000.0)  # converge por contrato
    # spot 0,10 % ×2 + trimestral 0,05 % (entrada) + liquidación 0,05 % (tomador, supuesto)
    fees = Q * 50_000 * 0.001 * 2 + Q * 51_000 * 0.0005 + Q * 50_000 * 0.0005
    assert tr.fees == pytest.approx(fees)
    assert tr.net == pytest.approx(Q * 1_000.0 - fees)


def test_perp_vs_quarterly_long_perp_pays_funding_until_expiry():
    sp, rate = SimParams(p_fail=0.0), 0.0001
    perp = flat(HOLD + 3, 50_000.0, start=D - HOLD * H)
    qt = quarterly("BTCUSDT_X", D, 50_500.0, settle=50_000.0, n_before=HOLD)
    long = Side_(perp, "usdm:BTCUSDT", "usdm")
    fs = Funding.of(funding(rate, HOLD + 3, start=D - HOLD * H))
    tr = futures_pair(_tr("basis"), _ex(FREE, sp), sp, P, long,
                      Side_(qt.bars, "usdm:BTCUSDT_Q1", "usdm"), q=Q, exit_t=D,
                      funding={long.key: fs}, settle=qt.settle)
    assert tr is not None and tr.exit_reason == "settle"
    k = HOLD // 8 - 1  # liquidaciones estrictamente entre la entrada y el vencimiento
    assert tr.settlements == k
    assert tr.funding == pytest.approx(-k * rate * Q * 50_000.0)
    assert tr.price_pnl == pytest.approx(Q * 500.0)


def test_cross_margin_liquidates_only_when_the_spread_eats_the_margin():
    sp = SimParams(p_fail=0.0)
    perp = flat(HOLD + 3, 50_000.0, start=D - HOLD * H)
    qt = quarterly("BTCUSDT_X", D, 50_500.0, settle=50_000.0, n_before=HOLD)
    qt.bars.c[100] = 75_000.0  # diferencial +48 %: el margen cruzado (×2) aguanta
    ok = futures_pair(_tr("basis"), _ex(FREE, sp), sp, P, Side_(perp, "usdm:BTCUSDT", "usdm"),
                      Side_(qt.bars, "usdm:BTCUSDT_Q1", "usdm"), q=Q, exit_t=D,
                      settle=qt.settle)
    assert ok is not None and ok.exit_reason == "settle"
    qt.bars.c[100] = 110_000.0  # diferencial que supera el margen de ambas patas
    tr = futures_pair(_tr("basis"), _ex(FREE, sp), sp, P, Side_(perp, "usdm:BTCUSDT", "usdm"),
                      Side_(qt.bars, "usdm:BTCUSDT_Q1", "usdm"), q=Q, exit_t=D,
                      settle=qt.settle)
    assert tr is not None and tr.exit_reason == "liq" and tr.liq_loss >= 0
    assert tr.net == pytest.approx(-Q * (50_000.0 + 50_500.0) / 2)  # se pierde el margen
