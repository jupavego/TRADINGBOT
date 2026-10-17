"""Reproducción del motor T38 sobre el histórico, panel, política, recomendación e informe."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from eim.arbitrage.params import ArbParams
from eim.arbitrage.sim import AssetHistory, DepthModel, SimParams
from eim.arbitrage.sim.calibrate import pick_threshold, recommend
from eim.arbitrage.sim.evaluate import Evaluator
from eim.arbitrage.sim.panel import build_panel, decision_times, policy
from eim.arbitrage.sim.replay import Replayer
from eim.arbitrage.sim.report import render
from eim.core import CostModel
from tests.arbitrage.helpers import T38
from tests.arbitrage.sim.helpers import T0, H, carry_history, flat, funding, profile, quarterly

P = ArbParams(assets=("BTC",), **T38)


def test_replay_sees_only_closed_bars_and_past_funding():
    n = 24 * 20
    prices = 50_000.0 + np.arange(n, dtype=float)
    hist = carry_history(rate=0.0002, n=n, spot=flat(n, prices), perp=flat(n, prices))
    t = T0 + 30 * 8 * H - H
    k = (t - T0) // H
    mkt = Replayer(hist, DepthModel(hist.depth), SimParams(), P).market_at(t)
    book = mkt.spot_books["BTCUSDT"]
    assert (book.bids[0][0] + book.asks[0][0]) / 2 == pytest.approx(prices[k - 1])
    prem = mkt.premium["BTCUSDT"]
    assert prem.next_funding_t == t + H and prem.funding_rate == 0.0002
    assert all(ts <= t for ts, _ in mkt.funding_hist["BTCUSDT"])
    future = prices.copy()
    future[k:] = 99_999.0  # cambiar el futuro no cambia lo que ve la decisión
    h2 = dataclasses.replace(hist, assets={"BTC": dataclasses.replace(
        hist.assets["BTC"], spot=flat(n, future), perp=flat(n, future))})
    mkt2 = Replayer(h2, DepthModel(h2.depth), SimParams(), P).market_at(t)
    assert mkt2.spot_books["BTCUSDT"].bids == book.bids
    assert mkt2.premium["BTCUSDT"].mark == prem.mark


def test_panel_realized_matches_engine_estimate_when_nothing_changes():
    hist = carry_history(rate=0.003, n=24 * 40)  # funding alto y constante: el motor elige
    panel = build_panel(hist, CostModel(), P, SimParams(p_fail=0.0),
                        strategies=("funding_carry",))
    rows = panel.of("funding_carry")
    sel = [r for r in rows if r.selected and r.trade is not None]
    assert sel and len(panel.times) == len(decision_times(hist, P, SimParams()))
    for r in sel:  # mismo libro, misma tasa: lo realizado = lo estimado por T38
        assert r.trade is not None
        assert r.trade.net_bps == pytest.approx(r.est_net_bps, abs=0.05)
    trades = policy(rows)
    assert trades and all(b.entry_t >= a.exit_t for a, b in zip(trades, trades[1:],
                                                                strict=False))


def test_recommend_disables_non_viable_strategies():
    res = {"verdicts": {"funding_carry": ("No viable", []), "basis": ("Marginal", []),
                        "related_perps": ("No viable", [])},
           "best_carry_h": 168.0, "strategies": {"basis": {"pick_theta": 5.0}},
           "calibration": {"pick": {"daily_move": 0.05}}, "sensitivity": {}}
    rec = {r["param"]: r for r in recommend(res, ArbParams())}
    assert rec["selectable"]["after"] == ("basis",)
    assert rec["carry_horizon_h"]["after"] == 168.0
    assert rec["min_net_bps"]["after"] == 5.0
    assert rec["daily_move"]["after"] == 0.05


def _rich_history():
    n = 24 * 50
    d = T0 + 8 * H * 140
    hist = carry_history(rate=0.0001, n=n)
    keys = ("usdm:BTCUSDT_Q1", "usdm:BTCUSDT_Q2", "usdcm:BTCUSDC", "spot:USDCUSDT")
    btc = dataclasses.replace(
        hist.assets["BTC"], usdc_perp=flat(n, 50_010.0), usdc_funding=funding(0.0001, n),
        quarterlies=(quarterly("BTCUSDT_Q", d, 50_400.0, settle=50_000.0,
                               n_before=(d - T0) // H),))
    return dataclasses.replace(
        hist, assets={"BTC": btc}, usdcusdt=flat(n, 1.0),
        depth=hist.depth + tuple(profile(k) for k in keys))


def test_evaluator_report_is_complete_and_declares_mode():
    hist = _rich_history()
    assert isinstance(hist.assets["BTC"], AssetHistory)
    ev = Evaluator(hist, CostModel(), P, SimParams(mc_paths=20))
    res = ev.run(sensitivities=False)
    assert set(res["verdicts"]) == {"funding_carry", "basis", "related_perps", "triangular"}
    assert all(v[0] in ("Viable", "Marginal", "No viable") for v in res["verdicts"].values())
    assert res["strategies"]["basis"]["counts"]["valued"] > 0
    assert res["strategies"]["related_perps"]["counts"]["valued"] > 0
    md = render(res, hist, CostModel(), P, SimParams(), T0)
    for section in ("Modo: ANÁLISIS", "## Veredicto", "## Supuestos", "Pata incompleta",
                    "## Oportunidades reales", "## Capital mínimo",
                    "## Parámetros del selector (T38)"):
        assert section in md
    # 1 pb cada 8 h en 24 h no cubre ~30 pb de comisiones: el carry del motor no entra
    assert res["strategies"]["funding_carry"]["counts"]["selected"] == 0


def test_threshold_pick_keeps_current_when_evidence_does_not_distinguish():
    def row(th, apr, n=100, lo=1.0, half=0.01):
        return {"theta": th, "n": n, "ci95": [lo, lo + 5], "policy_apr": apr,
                "policy_apr_half": half}

    sweep = [row(0.0, 0.040), row(2.0, 0.041), row(200.0, 0.045, n=40)]
    assert pick_threshold(sweep, 2.0) == 2.0  # 4,1 % está dentro del ruido de 4,5 %
    assert pick_threshold(sweep, 7.0) == 0.0  # el actual no está: el menor candidato
    tight = [row(0.0, 0.01, half=0.001), row(50.0, 0.05, half=0.001)]
    assert pick_threshold(tight, 2.0) == 50.0
    assert pick_threshold([row(0.0, 0.05, lo=-1.0)], 2.0) is None  # nada significativo
