"""Calibración T26 sobre el fixture de ETHUSDT 1h (sin red)."""
from __future__ import annotations

import json

import pytest

from eim.agents.plan import PlanAgent, PlanParams
from eim.backtest.engine import run_backtest
from eim.backtest.params import BacktestParams
from eim.backtest.strategy import PlanStrategy
from eim.calibration import nested
from eim.calibration.evaluate import Series, evaluate, run_window
from eim.calibration.inputs import InputCache
from eim.calibration.report import load_version, to_markdown, write_version
from eim.calibration.search import optimize
from eim.calibration.space import SPACE, build, defaults, n_changed, perturbations
from eim.synthesis import SynthesisParams
from tests.agents.conftest import make_snapshot

BT = BacktestParams(eval_step=6, lookback=250)


@pytest.fixture(scope="module")
def series() -> Series:
    cs = make_snapshot().candles
    return Series("ETHUSDT", "1h", cs, None, InputCache(cs, "ETHUSDT", "1h", BT.lookback))


def test_space_defaults_are_current_params_and_inside_bounds():
    base = defaults()
    for d in SPACE:
        assert d.low <= base[d.name] <= d.high, d.name
    plan, synth, tp = build(base)
    assert plan == PlanParams() and tp == 0
    assert synth.weights == {**SynthesisParams().weights, "structure": 1.0, "levels": 1.0}
    assert synth.model_copy(update={"weights": SynthesisParams().weights}) == SynthesisParams()
    assert n_changed(base, base) == 0


def test_perturbations_are_ten_percent_and_clipped():
    base = defaults()
    ps = dict(perturbations(base))
    assert ps["plan.min_rr+10%"]["plan.min_rr"] == pytest.approx(1.65)
    assert ps["plan.min_rr−10%"]["plan.min_rr"] == pytest.approx(1.35)
    assert not any(k.startswith("strategy.") for k in ps)       # categóricos: no
    edge = {**base, "plan.min_rr": 3.0}
    assert "plan.min_rr+10%" not in dict(perturbations(edge))  # recortado = sin cambio
    floats = {d.name for d in SPACE if d.kind == "float"}
    for k, v in ps.items():
        if k.split("+")[0].split("−")[0] in floats:
            assert n_changed(v, base) == 0                       # ±10 % no cuenta como cambio


def test_cached_inputs_match_full_agent(series):
    """Si la ventana móvil cubre todo el snapshot, el caché reproduce el agente exactamente."""
    snap = make_snapshot()
    snap = snap.model_copy(update={"candles": snap.candles[:240]})
    full = PlanAgent().run(snap)
    cache = InputCache(series.candles, "ETHUSDT", "1h", lookback=400)
    cached = PlanAgent(raw=cache).run(snap)
    assert cached.metrics["plan"] == full.metrics["plan"]
    assert cached.evidence == full.evidence


def test_default_values_reproduce_plain_plan_strategy(series):
    """`run_window(defaults)` sin caché == el backtest de T25 con `PlanStrategy()`."""
    bt = BacktestParams(eval_step=12, lookback=150)
    a, b = 300, 420
    ctx = a - bt.lookback
    ref = run_backtest(series.candles[ctx:b], None, PlanStrategy(), bt, trade_from=a - ctx,
                       sources={"candles": "?"})
    got = run_window(series, defaults(), a, b, bt, cached=False)
    assert got.trades_dicts() == ref.trades_dicts() and got.equity == ref.equity


def test_outer_folds_never_peek_and_are_aligned():
    folds = nested.outer_folds(5000, 500, train=1500, test=600, inner=3)
    assert len(folds) >= 2
    for f in folds:
        tr, (te,) = f["train"], f["test"]
        assert tr[-1][1] == te[0] and all(x[0] < x[1] for x in tr)
        assert all(i % 6 == 0 for w in tr + [te] for i in w)
    tests = [f["test"][0] for f in folds]
    assert all(b0 <= a1 for (_, b0), (a1, _) in zip(tests, tests[1:], strict=False))


def test_nested_optimizes_only_on_training(series, monkeypatch):
    seen = []
    real = nested.optimize

    def spy(s, windows, *a, **k):
        seen.append(windows)
        return real(s, windows, *a, **k)

    monkeypatch.setattr(nested, "optimize", spy)
    res = nested.run_nested(series, series, BT, train=360, test=180, inner=2, start=252,
                            n_trials=3, top_k=1, log=lambda _m: None)
    assert len(seen) == len(res["folds"]) >= 2
    for w, f in zip(seen, res["folds"], strict=True):
        assert series.candles[w[-1][1]].t == f["test_from_t"]     # termina donde empieza la prueba
    assert set(res["aggregate"]) == {"oos", "control"}
    assert isinstance(res["decision"]["accepted"], bool)
    rep = {"meta": {"symbol": "ETHUSDT", "timeframe": "1h", "control": "ETHUSDT", "source": "f",
                    "n_candles": 1, "first_t": 0, "last_t": 0, "data_hash": "h",
                    "objective": "o"}, "result": res, "fidelity": None, "notes": []}
    md = to_markdown(rep)
    assert "Dentro vs fuera de muestra" in md and "Degradación" in md


def test_optimize_is_reproducible_and_bounded(series):
    base = defaults()
    windows = [(252, 600), (600, 948)]
    r1 = optimize(series, windows, BT, base, n_trials=4, top_k=1, seed=1)
    r2 = optimize(series, windows, BT, base, n_trials=4, top_k=1, seed=1)
    assert r1.values == r2.values and r1.train_score == r2.train_score
    for d in SPACE:
        assert d.low <= r1.values[d.name] <= d.high
    assert r1.train_score >= r1.default_score            # el vigente es el primer trial
    ev = evaluate(series, base, windows, BT, base)
    assert ev.score == pytest.approx(r1.default_score)


def test_decide_keeps_previous_values_when_oos_does_not_improve(tmp_path):
    fold = {"test": {"default": {"median_sharpe": 0.5}, "calibrated": {"median_sharpe": 0.2}},
            "kept_default": False, "values": {**defaults(), "plan.min_rr": 2.5}}
    agg = {"oos": {"default": {"median_window_sharpe": 0.5},
                   "calibrated": {"median_window_sharpe": 0.2}}}
    dec = nested.decide([fold], agg)
    assert not dec["accepted"] and dec["reasons"]
    rep = {"result": {"decision": dec, "folds": [fold], "base": defaults()},
           "meta": {"data_hash": "h", "symbol": "ETHUSDT", "timeframe": "1h"}}
    p = write_version(rep, "v_test", tmp_path)
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["values"] == defaults() and doc["candidate"]["plan.min_rr"] == 2.5
    plan, _, _ = load_version(p)
    assert plan == PlanParams()
