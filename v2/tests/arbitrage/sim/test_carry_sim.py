"""Carry simulado: funding constante = retorno analítico, costos exactos, libro delgado,
pata incompleta, rebalanceo y liquidación."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from eim.arbitrage.params import ArbParams
from eim.arbitrage.sim import ArbHistory, DepthModel, Funding, SimParams, SimTrade
from eim.arbitrage.sim.hedge import Side_, spot_short
from eim.arbitrage.sim.stats import incident_losses, latency_returns, mc_nets
from eim.arbitrage.sim.trade import Executor
from eim.core import CostModel
from tests.arbitrage.helpers import T38
from tests.arbitrage.sim.helpers import FREE, T0, H, carry_history, flat, profile

P = ArbParams(assets=("BTC",), **T38)
N = 10_000.0
ENTRY = T0 + 20 * 8 * H - H  # 1 h antes de una liquidación


def _carry(hist: ArbHistory, cm: CostModel, sp: SimParams, hours: int,
           entry: int = ENTRY) -> SimTrade:
    h = hist.assets["BTC"]
    assert h.spot is not None and h.perp is not None
    price = float(h.spot.o[h.spot.at(entry)])
    tr = SimTrade(strategy="funding_carry", variant="largo spot / corto perpetuo", asset="BTC",
                  instrument="BTCUSDT", entry_t=entry, capital=N * 1.5, notional=N)
    refs = hist.depth_ref_vq
    out = spot_short(tr, Executor(cm, DepthModel(hist.depth), sp), sp, P,
                     Side_(h.spot, "spot:BTCUSDT", "spot", refs.get("spot:BTCUSDT")),
                     Side_(h.perp, "usdm:BTCUSDT", "usdm", refs.get("usdm:BTCUSDT")),
                     q=N / price, exit_t=entry + hours * H, funding=Funding.of(h.funding))
    assert out is not None
    return out


def test_constant_funding_gives_analytic_return():
    rate = 0.0001
    tr = _carry(carry_history(rate, levels=((0.0, 1e12),)), FREE, SimParams(p_fail=0.0), 720)
    assert tr.settlements == 90  # 30 días × 3 liquidaciones
    assert tr.funding == pytest.approx(90 * rate * N)
    assert tr.price_pnl == pytest.approx(0.0, abs=1e-9)
    assert tr.net == pytest.approx(90 * rate * N)
    apr = tr.net / tr.capital * 8760 / tr.hold_h
    assert apr == pytest.approx(rate * 3 * 365 / 1.5)  # capital = spot + margen a ×2


def test_costs_are_subtracted_exactly():
    rate = 0.0001
    tr = _carry(carry_history(rate), CostModel(), SimParams(p_fail=0.01), 24)
    assert tr.settlements == 3
    fees = 2 * (0.0010 + 0.0005) * N  # spot y perpetuo, entrada y salida (VIP 0 tomador)
    slip = 4 * 0.5e-4 * N  # perfil a 0,5 pb del medio
    legging = 0.01 * 2 * (0.0010 * N + 0.5e-4 * N) * 2  # deshacer la pata spot × 2 ejecuciones
    assert tr.fees == pytest.approx(fees)
    assert tr.slippage == pytest.approx(slip)
    assert tr.legging == pytest.approx(legging)
    assert tr.net == pytest.approx(3 * rate * N - fees - slip - legging)
    assert tr.net < 0  # 3 pb de funding no pagan 30 pb de comisiones


LEVELS = ((0.5, 20_000.0), (5.0, 20_000.0), (25.0, 1e12))


def test_profile_walks_levels_and_flags_incomplete():
    prof = profile("x", ((1.0, 1_000.0), (3.0, 1_000.0)))
    cost, ok = prof.cost(1_500.0, "buy")
    assert ok and cost == pytest.approx(1_000 * 1e-4 + 500 * 3e-4)
    cost, ok = prof.cost(3_000.0, "sell")
    assert not ok and cost == pytest.approx(1_000 * 1e-4 + 2_000 * 3e-4)


def test_thin_book_reduces_net():
    base = _carry(carry_history(levels=LEVELS), CostModel(), SimParams(), 24)
    thin = _carry(carry_history(levels=LEVELS), CostModel(), SimParams(depth_scale=0.1), 24)
    assert base.slippage == pytest.approx(4 * 0.5e-4 * N)
    # ×0,1: 2 000 a 0,5 pb + 2 000 a 5 pb + 6 000 a 25 pb por pata
    assert thin.slippage == pytest.approx(4 * (2_000 * 0.5e-4 + 2_000 * 5e-4 + 6_000 * 25e-4))
    assert thin.net < base.net


def test_low_historical_volume_thins_the_captured_book():
    hist = carry_history(levels=LEVELS)
    quiet = dataclasses.replace(hist, depth_ref_vq={"spot:BTCUSDT": 1e10, "usdm:BTCUSDT": 1e10})
    base = _carry(hist, CostModel(), SimParams(), 24)
    thin = _carry(quiet, CostModel(), SimParams(vol_scale_min=0.2), 24)
    assert thin.slippage > base.slippage and thin.net < base.net


def test_incomplete_leg_generates_loss():
    clean = _carry(carry_history(), CostModel(), SimParams(p_fail=0.0), 24)
    risky = _carry(carry_history(), CostModel(), SimParams(p_fail=1.0), 24)
    undo = 2 * (0.0010 * N + 0.5e-4 * N)  # deshacer la pata spot: ida y vuelta
    assert clean.legging == 0
    assert risky.legging == pytest.approx(2 * undo)  # entrada y salida
    assert risky.net == pytest.approx(clean.net - 2 * undo)
    rets = np.random.default_rng(1).normal(0, 0.003, 5_000)  # rend. de 15 min
    loss = incident_losses(undo / N, latency_returns(rets, 1_000.0), 20_000,
                           np.random.default_rng(0))
    assert loss.mean() > 0 and np.percentile(loss, 99) > undo / N
    mc = mc_nets([risky], {"BTC": rets}, SimParams(p_fail=1.0, mc_paths=400))
    assert mc.max() < clean.net - undo  # cada camino pierde ≥ un incidente


def test_rally_rebalances_margin_without_liquidation():
    n = 24 * 30
    up = np.linspace(100.0, 250.0, n)
    hist = carry_history(rate=0.0, n=n, spot=flat(n, up), perp=flat(n, up),
                         levels=((0.0, 1e12),))
    tr = _carry(hist, FREE, SimParams(p_fail=0.0), 600, entry=T0 + 7 * H)
    assert tr.rebalances >= 1 and tr.exit_reason == "time" and tr.liq_loss == 0
    assert tr.price_pnl == pytest.approx(0.0, abs=1e-6)  # cubierto: sin cambio de base
    assert tr.net == pytest.approx(0.0, abs=1e-6)


def test_spike_beyond_liquidation_loses_the_margin():
    n = 24 * 10
    perp = flat(n, 100.0)
    perp.h[60] = 160.0  # mecha intra-vela más allá del precio de liquidación (×2)
    hist = carry_history(rate=0.0, n=n, spot=flat(n, 100.0), perp=perp, levels=((0.0, 1e12),))
    tr = _carry(hist, FREE, SimParams(p_fail=0.0), 120, entry=T0 + 7 * H)
    q = N / 100.0
    assert tr.exit_reason == "liq" and tr.liq_loss > 0
    assert tr.net == pytest.approx(-q * 100.0 / 2)  # se pierde todo el margen; el spot queda
