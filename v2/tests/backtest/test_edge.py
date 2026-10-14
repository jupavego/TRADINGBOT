"""Tests de la estadística de la puerta de edge (T27): réplica, nulo aleatorio y pruebas."""

from __future__ import annotations

import numpy as np

from eim.backtest.edge import (
    Decision,
    RecordingStrategy,
    ReplayStrategy,
    buy_hold_returns,
    flip,
    holm,
    mean_pvalue,
    perm_pvalue,
    sharpe_diff_pvalue,
)
from eim.backtest.engine import run_backtest
from eim.backtest.params import BacktestParams
from eim.backtest.strategy import Signal
from eim.core import Candle, MarketSnapshot


def _candles(n: int = 400, seed: int = 1) -> list[Candle]:
    rng = np.random.default_rng(seed)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    out, prev = [], px[0]
    for i, c in enumerate(px):
        o = prev
        out.append(Candle(t=i * 3_600_000, o=o, h=max(o, c) * 1.002, l=min(o, c) * 0.998, c=c,
                          v=1000.0))
        prev = c
    return out


class _Every:
    """Estrategia de juguete: largo cada 10 velas con SL/TP a ±1 %/±1.5 %."""

    def on_bar(self, snap: MarketSnapshot) -> Signal | None:
        c = snap.candles[-1]
        if (c.t // 3_600_000) % 10:
            return None
        return Signal(side=1, sl=c.c * 0.99, tp=c.c * 1.015, tag=str(c.t))


def test_replay_reproduces_recorded_strategy():
    cs, bt = _candles(), BacktestParams(lookback=50)
    rec = RecordingStrategy(_Every())
    a = run_backtest(cs, None, rec, bt)
    b = run_backtest(cs, None, ReplayStrategy(rec.decisions), bt)
    assert a.trades and [t.entry_t for t in a.trades] == [t.entry_t for t in b.trades]
    assert a.equity == b.equity


def test_random_replay_flips_some_sides_with_same_geometry():
    cs, bt = _candles(), BacktestParams(lookback=50)
    rec = RecordingStrategy(_Every())
    run_backtest(cs, None, rec, bt)
    res = run_backtest(cs, None, ReplayStrategy(rec.decisions, np.random.default_rng(3)), bt)
    sides = {t.side for t in res.trades}
    assert sides == {1, -1}


def test_flip_mirrors_stop_and_target():
    s = flip(Decision(100.0, Signal(side=1, sl=98.0, tp=103.0)))
    assert (s.side, s.sl, s.tp) == (-1, 102.0, 97.0)


def test_buy_hold_returns_cover_window():
    cs = _candles(50)
    r = buy_hold_returns(cs, 10, 20)
    assert len(r) == 10
    assert np.isclose(r[0], cs[10].c / cs[9].c - 1)


def test_perm_pvalue_bounds():
    null = np.arange(99.0)
    assert perm_pvalue(1000.0, null) == 0.01
    assert perm_pvalue(-1.0, null) == 1.0


def test_mean_pvalue_detects_positive_mean_and_not_zero_mean():
    rng = np.random.default_rng(0)
    assert mean_pvalue(rng.normal(0.5, 1, 300)) < 0.01
    assert mean_pvalue(rng.normal(-0.5, 1, 300)) > 0.5


def test_sharpe_diff_pvalue_orders_strategies():
    rng = np.random.default_rng(0)
    good, bad = rng.normal(0.002, 0.01, 2000), rng.normal(-0.002, 0.01, 2000)
    p, ci = sharpe_diff_pvalue(good, bad, 8766.0, n_boot=300)
    assert p < 0.05 and ci[0] > 0
    p2, _ = sharpe_diff_pvalue(bad, good, 8766.0, n_boot=300)
    assert p2 > 0.95


def test_holm_adjustment():
    adj = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert np.isclose(adj["a"], 0.03)
    assert np.isclose(adj["c"], 0.06)
    assert np.isclose(adj["b"], 0.06)      # monótono: nunca menor que el anterior
    assert holm({"x": 0.9, "y": 0.8}) == {"y": 1.0, "x": 1.0}   # acotado en 1
