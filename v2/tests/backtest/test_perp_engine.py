"""Integridad del simulador: sin look-ahead, costos cero = bruto, liquidación, funding."""
from __future__ import annotations

import numpy as np
import pytest

from eim.backtest.engine import run_backtest
from eim.backtest.metrics import compute_metrics, cost_breakdown, max_drawdown, profit_factor
from eim.backtest.params import ZERO_COSTS, BacktestParams, CostParams
from eim.backtest.perp import exit_in_bar, liquidation_price
from eim.backtest.strategy import Signal
from eim.backtest.walkforward import make_windows
from eim.core import Candle, MarketSnapshot

H = 3_600_000


def bars(prices: list[tuple[float, float, float, float]], t0: int = 0, v: float = 1e6):
    return [Candle(t=t0 + i * H, o=o, h=h, l=lo, c=c, v=v)
            for i, (o, h, lo, c) in enumerate(prices)]


def flat(n: int, p: float = 100.0, t0: int = 0):
    return bars([(p, p + 0.5, p - 0.5, p)] * n, t0)


class At:
    """Estrategia guionizada: emite `sig` al cerrar la vela de índice `i`."""

    def __init__(self, i: int, sig: Signal) -> None:
        self.i, self.sig = i, sig
        self.seen: list[MarketSnapshot] = []

    def on_bar(self, snap: MarketSnapshot) -> Signal | None:
        self.seen.append(snap)
        return self.sig if len(self.seen) - 1 == self.i else None


P0 = BacktestParams(costs=ZERO_COSTS, max_hold_bars=0)


# --- mecánica -------------------------------------------------------------
def test_liquidation_price_known_cases():
    assert liquidation_price(1, 100, 10, 0.005) == pytest.approx(90.5)
    assert liquidation_price(-1, 100, 10, 0.005) == pytest.approx(109.5)
    assert liquidation_price(1, 2000, 5, 0.005) == pytest.approx(2000 * (1 - 0.195))


def test_sl_before_tp_when_both_fit_in_same_bar():
    c = Candle(t=0, o=100, h=110, l=90, c=100, v=1)
    assert exit_in_bar(1, 95, 105, 50, c) == ("sl", 95)
    assert exit_in_bar(-1, 105, 95, 150, c) == ("sl", 105)
    assert exit_in_bar(1, 95, 105, 50, Candle(t=0, o=100, h=106, l=99, c=100, v=1)) == ("tp", 105)
    assert exit_in_bar(1, 95, 105, 50, Candle(t=0, o=100, h=101, l=99, c=100, v=1)) is None


def test_gap_through_stop_fills_at_open():
    c = Candle(t=0, o=90, h=92, l=88, c=91, v=1)
    assert exit_in_bar(1, 95, 105, 50, c) == ("sl", 90)


def test_liquidation_precedes_stop_placed_beyond_it():
    c = Candle(t=0, o=100, h=100, l=80, c=85, v=1)
    assert exit_in_bar(1, 85, 120, 90.5, c) == ("liq", 90.5)


# --- ejecución sin anticipación ------------------------------------------
def test_executes_on_next_bar_open_never_same_bar():
    cs = flat(12)
    cs[6] = Candle(t=6 * H, o=101.0, h=101.5, l=100.5, c=101.0, v=1e6)
    strat = At(5, Signal(side=1, sl=95, tp=108))
    res = run_backtest(cs, None, strat, P0)
    t = res.trades[0]
    assert t.entry_t == cs[6].t and t.entry_ref == 101.0   # apertura de la vela siguiente


def test_strategy_never_sees_future_candles():
    cs = flat(30)
    strat = At(99, Signal(1, 90, 110))
    run_backtest(cs, [(0, 0.0001), (8 * H, 0.0001), (16 * H, 0.0001), (24 * H, 0.0001)], strat, P0)
    for k, s in enumerate(strat.seen):
        assert s.candles[-1].t == cs[k].t
        assert s.asof == cs[k].t + H
        assert all(t < s.asof for t, _ in (s.funding or []))


def _walk(n: int, seed: int) -> list[Candle]:
    rng = np.random.default_rng(seed)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    out, prev = [], 100.0
    for i, c in enumerate(px):
        hi, lo = max(prev, c) * 1.004, min(prev, c) * 0.996
        out.append(Candle(t=i * H, o=float(prev), h=float(hi), l=float(lo), c=float(c), v=1e5))
        prev = c
    return out


class Momentum:
    """Determinista y con estado propio: largo/corto según la deriva de las últimas 20 velas."""

    def on_bar(self, snap: MarketSnapshot) -> Signal | None:
        cs = snap.candles
        if len(cs) < 25 or len(cs) % 7:
            return None
        c = cs[-1].c
        side = 1 if c > np.mean([x.c for x in cs[-20:]]) else -1
        return Signal(side=side, sl=c * (1 - 0.02 * side), tp=c * (1 + 0.03 * side))


def test_future_data_does_not_change_past_trades():
    cut = 300
    base = _walk(500, seed=1)
    altered = base[:cut] + [Candle(t=c.t, o=c.o * 3, h=c.h * 3, l=c.l * 3, c=c.c * 3, v=c.v * 9)
                            for c in base[cut:]]
    p = BacktestParams(max_hold_bars=48)
    a = run_backtest(base, None, Momentum(), p)
    b = run_backtest(altered, None, Momentum(), p)
    past_a = [t for t in a.trades if t.exit_t < base[cut].t]
    past_b = [t for t in b.trades if t.exit_t < base[cut].t]
    assert len(past_a) >= 5
    assert past_a == past_b
    assert a.equity[:cut] == b.equity[:cut]


# --- costos --------------------------------------------------------------
def test_zero_costs_reproduce_gross_pnl():
    cs = _walk(400, seed=2)
    res = run_backtest(cs, [(t, 0.0) for t in range(0, 400 * H, 8 * H)], Momentum(), P0)
    assert len(res.trades) >= 5
    for t in res.trades:
        assert t.net_pnl == pytest.approx(t.gross_pnl)
        assert t.gross_pnl == pytest.approx(t.side * (t.exit_ref - t.entry_ref) * t.qty)
    assert res.equity[-1] == pytest.approx(P0.initial_equity + sum(t.gross_pnl for t in res.trades)
                                           - sum(t.funding for t in res.trades))


def test_cost_breakdown_reconciles_with_equity():
    cs = _walk(400, seed=3)
    fnd = [(t, 0.0002) for t in range(0, 400 * H, 8 * H)]
    p = BacktestParams(max_hold_bars=48)
    res = run_backtest(cs, fnd, Momentum(), p)
    d = cost_breakdown(res)
    assert d["fees"] > 0 and d["slippage"] > 0 and d["funding"] != 0
    assert d["gross_pnl"] - d["total_costs"] == pytest.approx(d["net_pnl"])
    assert res.equity[-1] == pytest.approx(p.initial_equity + d["net_pnl"])
    assert d["funding_settlements"]["expected"] >= d["funding_settlements"]["observed"] > 0


def test_funding_paid_by_longs_received_by_shorts():
    cs = flat(30)                                  # 30 h; fundings en t=0, 8 h, 16 h, 24 h
    fnd = [(k * 8 * H, 0.001) for k in range(4)]
    for side in (1, -1):
        sig = Signal(side, sl=100 - 20 * side, tp=100 + 20 * side)
        res = run_backtest(cs, fnd, At(1, sig), P0)  # entra en la vela 2 (t=2 h)
        t = res.trades[0]
        assert t.entry_t == 2 * H
        # liquidaciones a 8, 16 y 24 h (la de t=0 es anterior a la entrada)
        assert t.funding == pytest.approx(side * t.qty * 100.0 * 0.001 * 3)


def test_missing_funding_is_flagged():
    res = run_backtest(flat(30), None, At(1, Signal(1, 80, 120)), P0)
    d = cost_breakdown(res)
    assert d["funding_settlements"]["observed"] == 0 < d["funding_settlements"]["expected"]
    assert "warning_funding" in d


def test_fees_and_slippage_hurt_longs_and_shorts():
    cs = flat(20)
    cs[8] = Candle(t=8 * H, o=100, h=106, l=99, c=105, v=1e6)    # toca el TP del largo
    cp = CostParams(taker_fee=0.001, maker_fee=0.0005, slip_base_bps=5, slip_vol_k=0,
                    slip_impact_k=0)
    p = BacktestParams(costs=cp, max_hold_bars=0)
    res = run_backtest(cs, None, At(2, Signal(1, 95, 105)), p)
    t = res.trades[0]
    assert t.reason == "tp"
    assert t.entry_fill == pytest.approx(100 * 1.0005)
    assert t.fees == pytest.approx(0.001 * t.qty * t.entry_fill + 0.0005 * t.qty * 105)
    assert t.net_pnl < t.gross_pnl


def test_liquidation_loses_exactly_the_margin():
    cs = flat(12)
    cs[6] = Candle(t=6 * H, o=100, h=100, l=85, c=86, v=1e6)    # cae por debajo de 90.5
    p = BacktestParams(costs=ZERO_COSTS, leverage=10,
                       risk_frac=0.5, max_hold_bars=0)
    res = run_backtest(cs, None, At(2, Signal(1, sl=80, tp=130)), p)   # SL más allá de la liq.
    t = res.trades[0]
    assert t.reason == "liq" and t.exit_ref == pytest.approx(90.5)
    margin = t.qty * t.entry_ref / 10
    assert t.gross_pnl - t.liq_fee == pytest.approx(-margin)
    assert res.equity[-1] == pytest.approx(p.initial_equity - margin)


def test_stop_loss_loss_is_one_r_without_costs():
    cs = flat(12)
    cs[6] = Candle(t=6 * H, o=100, h=100.2, l=94, c=95, v=1e6)
    res = run_backtest(cs, None, At(2, Signal(1, 95, 110)), P0)
    t = res.trades[0]
    assert t.reason == "sl" and t.r_multiple == pytest.approx(-1.0)
    assert t.net_pnl == pytest.approx(-P0.initial_equity * P0.risk_frac)


def test_end_of_data_closes_open_position():
    res = run_backtest(flat(10), None, At(2, Signal(1, 50, 150)), P0)
    assert res.trades[0].reason == "end"


# --- walk-forward y métricas ---------------------------------------------
def test_walkforward_windows_are_disjoint_and_causal():
    ws = make_windows(1000, train=300, test=200, warmup=50)
    assert len(ws) == 3
    for a, b in zip(ws, ws[1:], strict=False):
        assert a["test_to"] <= b["test_from"]
    for w in ws:
        assert w["ctx_from"] <= w["test_from"] and w["train_from"] + 300 == w["test_from"]


def test_metrics_known_values_and_seeded_bootstrap():
    assert profit_factor(np.array([2.0, -1.0, 1.0])) == pytest.approx(3.0)
    assert profit_factor(np.array([1.0, 2.0])) is None
    assert max_drawdown(np.array([100.0, 120.0, 90.0, 130.0])) == pytest.approx(0.25)
    res = run_backtest(_walk(500, seed=4), None, Momentum(), BacktestParams())
    a = compute_metrics(res, 10_000, 8766, seed=7, n_boot=200)
    b = compute_metrics(res, 10_000, 8766, seed=7, n_boot=200)
    assert a == b
    assert a["n_trades"] == len(res.trades)
    lo, hi = a["ci95"]["expectancy_r"]
    assert lo <= a["expectancy_r"] <= hi
    assert 0 <= a["exposure"] <= 1
