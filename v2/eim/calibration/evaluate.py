"""Evaluación de un juego de parámetros sobre ventanas y objetivo robusto (no solo retorno)."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from eim.agents.plan import PlanAgent
from eim.backtest.engine import BacktestResult, run_backtest
from eim.backtest.metrics import compute_metrics
from eim.backtest.params import BacktestParams
from eim.backtest.report import pool
from eim.backtest.strategy import PlanStrategy
from eim.calibration.inputs import InputCache
from eim.calibration.space import build, n_changed
from eim.core import Candle


@dataclass
class Series:
    """Serie de un símbolo con su caché de insumos."""

    symbol: str
    timeframe: str
    candles: list[Candle]
    funding: list[tuple[int, float]] | None
    cache: InputCache
    source: str = "?"


@dataclass(frozen=True)
class ObjectiveParams:
    """Objetivo = mediana de Sharpe por ventana − λ_dd·peor DD − λ_k·nº de parámetros movidos.

    Con menos de `min_trades` operaciones en total la cifra no es evaluable y se castiga.
    """

    dd_penalty: float = 2.0          # 10 % de DD resta 0.2 de Sharpe anual
    param_penalty: float = 0.05      # por parámetro que se aparta >10 % del vigente
    min_trades: int = 20
    few_trades_score: float = -5.0


DEFAULT_OBJECTIVE = ObjectiveParams()


@dataclass
class Evaluation:
    windows: list[dict] = field(default_factory=list)   # métricas por ventana
    results: list[BacktestResult] = field(default_factory=list)
    score: float = 0.0
    median_sharpe: float = 0.0
    worst_dd: float = 0.0
    n_trades: int = 0


def run_window(series: Series, values: dict, a: int, b: int, bt: BacktestParams,
               cached: bool = True) -> BacktestResult:
    """Backtest de `[a, b)` con contexto previo de `lookback` velas (solo pasado)."""
    plan, synth, tp_index = build(values)
    agent = PlanAgent(plan, synth, raw=series.cache if cached else None)
    ctx = max(0, a - bt.lookback)
    return run_backtest(series.candles[ctx:b], series.funding, PlanStrategy(agent, tp_index), bt,
                        symbol=series.symbol, timeframe=series.timeframe, trade_from=a - ctx,
                        sources={"candles": series.source})


def evaluate(series: Series, values: dict, windows: list[tuple[int, int]], bt: BacktestParams,
             base: dict, op: ObjectiveParams = DEFAULT_OBJECTIVE, cached: bool = True
             ) -> Evaluation:
    ev = Evaluation()
    for a, b in windows:
        res = run_window(series, values, a, b, bt, cached)
        m = compute_metrics(res, bt.initial_equity, bt.bars_per_year, n_boot=0)
        ev.results.append(res)
        ev.windows.append({"from_t": series.candles[a].t, "to_t": series.candles[b - 1].t,
                           "sharpe": m["sharpe"], "max_drawdown": m["max_drawdown"],
                           "total_return": m["total_return"], "n_trades": m["n_trades"],
                           "expectancy_r": m["expectancy_r"], "win_rate": m["win_rate"]})
    ev.median_sharpe = statistics.median(w["sharpe"] for w in ev.windows) if ev.windows else 0.0
    ev.worst_dd = max((w["max_drawdown"] for w in ev.windows), default=0.0)
    ev.n_trades = sum(w["n_trades"] for w in ev.windows)
    ev.score = score_of(ev, values, base, op)
    return ev


def score_of(ev: Evaluation, values: dict, base: dict, op: ObjectiveParams) -> float:
    if ev.n_trades < op.min_trades:
        return op.few_trades_score
    return (ev.median_sharpe - op.dd_penalty * ev.worst_dd
            - op.param_penalty * n_changed(values, base))


def pooled_metrics(ev: Evaluation, bt: BacktestParams, seed: int = 0) -> dict:
    """Métricas agregadas de todas las ventanas (con IC por bootstrap)."""
    keep = ("n_trades", "total_return", "sharpe", "sortino", "max_drawdown", "expectancy_r",
            "win_rate", "profit_factor", "exposure", "ci95")
    m = compute_metrics(pool(ev.results, bt.initial_equity), bt.initial_equity, bt.bars_per_year,
                        seed=seed)
    out = {k: m.get(k) for k in keep}
    out["median_window_sharpe"] = ev.median_sharpe
    out["worst_window_dd"] = ev.worst_dd
    return out
