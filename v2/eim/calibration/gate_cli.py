"""CLI de la puerta de edge (T27): evidencia fuera de muestra → `reports/edge/edge_results.json`.

    python -m eim.calibration.gate_cli --store data --symbols BTCUSDT ETHUSDT --null 500

Evalúa los parámetros VIGENTES (no calibra nada) en ventanas disjuntas, contra comprar y
mantener y contra entrada aleatoria con el mismo riesgo; añade la calibración de escenarios
(backfill T19 con orígenes sin solape). El veredicto lo redacta el informe `reports/edge_gate.md`.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from eim.agents.plan import PlanAgent
from eim.backtest.edge import (
    RecordingStrategy,
    ReplayStrategy,
    buy_hold_returns,
    holm,
    mean_pvalue,
    perm_pvalue,
    sharpe_diff_pvalue,
)
from eim.backtest.engine import BacktestResult, run_backtest
from eim.backtest.metrics import _sharpe, compute_metrics
from eim.backtest.params import BacktestParams
from eim.backtest.report import data_hash, pool
from eim.backtest.strategy import PlanStrategy, Strategy
from eim.calibration.cli import load_series
from eim.calibration.evaluate import Series
from eim.calibration.space import build, defaults
from eim.data.store import Store

OUT = Path("reports/edge")


def windows_for(ref: Series, s: Series, start: int, size: int) -> list[tuple[int, int]]:
    """Ventanas disjuntas de `size` velas definidas en `ref` y llevadas a `s` por fecha."""
    start += -start % 6
    idx = {c.t: i for i, c in enumerate(s.candles)}
    out = []
    for a in range(start, len(ref.candles) - size + 1, size):
        ia, ib = idx.get(ref.candles[a].t), idx.get(ref.candles[a + size - 1].t)
        if ia is not None and ib is not None and ib - ia == size - 1:
            out.append((ia, ib + 1))
    return out


def run(s: Series, w: tuple[int, int], strat: Strategy, bt: BacktestParams) -> BacktestResult:
    a, b = w
    ctx = max(0, a - bt.lookback)
    return run_backtest(s.candles[ctx:b], s.funding, strat, bt, symbol=s.symbol,
                        timeframe=s.timeframe, trade_from=a - ctx,
                        sources={"candles": s.source})


def _returns(res: BacktestResult) -> np.ndarray:
    eq = np.array(res.equity, float)
    return np.diff(eq) / eq[:-1] if len(eq) > 1 else np.array([])


def gross_r(trades: list) -> np.ndarray:
    """R bruto (antes de costos) por operación: diagnóstico de habilidad direccional."""
    return np.array([t.gross_pnl / max(t.qty * abs(t.entry_ref - t.sl), 1e-12) for t in trades])


def analyze(s: Series, wins: list[tuple[int, int]], bt: BacktestParams, n_null: int,
            seed: int, log) -> dict:
    plan, synth, tp = build(defaults())
    results, decs = [], []
    for w in wins:
        rec = RecordingStrategy(PlanStrategy(PlanAgent(plan, synth, raw=s.cache), tp))
        res = run(s, w, rec, bt)
        rep = run(s, w, ReplayStrategy(rec.decisions), bt)        # control de fidelidad
        assert [t.entry_t for t in rep.trades] == [t.entry_t for t in res.trades]
        results.append(res)
        decs.append(rec.decisions)
    ppy = bt.bars_per_year
    pooled = pool(results, bt.initial_equity)
    m = compute_metrics(pooled, bt.initial_equity, ppy, seed=seed)
    r_s = _returns(pooled)
    r_bh = np.concatenate([buy_hold_returns(s.candles, a, b) for a, b in wins])[1:]
    p_bh, ci_bh = sharpe_diff_pvalue(r_s, r_bh, ppy, seed=seed)
    per_w = []
    for (a, b), res in zip(wins, results, strict=True):
        mw = compute_metrics(res, bt.initial_equity, ppy, n_boot=0)
        per_w.append({"from_t": s.candles[a].t, "to_t": s.candles[b - 1].t,
                      "sharpe": mw["sharpe"], "total_return": mw["total_return"],
                      "max_drawdown": mw["max_drawdown"], "n_trades": mw["n_trades"],
                      "expectancy_r": mw["expectancy_r"],
                      "bh_sharpe": _sharpe(buy_hold_returns(s.candles, a, b), ppy)})
    rng = np.random.default_rng(seed)
    null_sh, null_er, null_gr = [], [], []
    t0 = time.time()
    for k in range(n_null):
        rs = [run(s, w, ReplayStrategy(d, rng), bt) for w, d in zip(wins, decs, strict=True)]
        pr = pool(rs, bt.initial_equity)
        null_sh.append(_sharpe(_returns(pr), ppy))
        rr = [t.r_multiple for t in pr.trades]
        null_er.append(float(np.mean(rr)) if rr else 0.0)
        null_gr.append(float(gross_r(pr.trades).mean()) if pr.trades else 0.0)
        if (k + 1) % 50 == 0:
            log(f"  {s.symbol}: nulo {k + 1}/{n_null} ({time.time() - t0:.0f} s)")
    rr = np.array([t.r_multiple for t in pooled.trades])
    gr = gross_r(pooled.trades)
    return {"symbol": s.symbol, "n_windows": len(wins), "windows": per_w,
            "metrics": {k: m.get(k) for k in ("n_trades", "total_return", "sharpe", "sortino",
                                              "max_drawdown", "expectancy_r", "win_rate",
                                              "profit_factor", "exposure", "ci95")},
            "buy_hold": {"sharpe": _sharpe(r_bh, ppy),
                         "total_return": float(np.prod(1 + r_bh) - 1),
                         "p_strategy_gt_bh": p_bh, "ci95_sharpe_diff": ci_bh},
            "random": {"n": n_null, "sharpe_mean": float(np.mean(null_sh)),
                       "sharpe_p5_p95": [float(np.percentile(null_sh, 5)),
                                         float(np.percentile(null_sh, 95))],
                       "expectancy_r_mean": float(np.mean(null_er)),
                       "p_sharpe": perm_pvalue(m["sharpe"], null_sh),
                       "p_expectancy": perm_pvalue(float(rr.mean()) if len(rr) else 0.0,
                                                   null_er)},
            "diagnostic": {"gross_r_mean": float(gr.mean()) if len(gr) else None,
                           "cost_r_mean": float((gr - rr).mean()) if len(gr) else None,
                           "random_gross_r_mean": float(np.mean(null_gr)),
                           "p_gross_vs_random": perm_pvalue(float(gr.mean()) if len(gr)
                                                            else 0.0, null_gr),
                           "p_gross_gt0": mean_pvalue(gr, seed=seed)},
            "p_expectancy_gt0": mean_pvalue(rr, seed=seed),
            "frac_windows_sharpe_pos": float(np.mean([w["sharpe"] > 0 for w in per_w])),
            "data_hash": data_hash(s.candles, s.funding), "source": s.source}


def scenario_calibration(s: Series, horizon: int, max_origins: int) -> dict:
    """Backfill T19 con orígenes cada `horizon` velas (sin solape → muestra independiente)."""
    from eim.forecast.backfill import backfill
    from eim.forecast.base_engine import BaseEngine
    from eim.forecast.calibration import evaluate_forecast, summarize

    closes = {c.t: c.c for c in s.candles}
    outs = []
    for fs in backfill(BaseEngine(), s.candles, symbol=s.symbol, timeframe=s.timeframe,
                       horizon=horizon, stride=horizon, max_origins=max_origins):
        o = evaluate_forecast(fs, closes)
        if o is not None:
            outs.append(o)
    rep = summarize(outs, horizon)
    rep["n_effective"] = len(outs)          # orígenes sin solape: cada uno es independiente
    rep.pop("curve", None)
    return rep


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True)
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--window", type=int, default=4380)
    ap.add_argument("--start", type=int, default=504)
    ap.add_argument("--null", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fc-origins", type=int, default=400)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    bt = BacktestParams(eval_step=6)
    store, cdir = Store(a.store), Path("reports/calibration/cache")
    loaded = [load_series(store, sym, a.tf, bt.lookback, cdir) for sym in a.symbols]
    series = [x[0] for x in loaded]
    out: dict = {"meta": {"mode": "SIMULADO", "timeframe": a.tf, "window": a.window,
                          "params": defaults(), "backtest": bt.model_dump(),
                          "seed": a.seed}, "assets": {}}
    for s in series:
        wins = windows_for(series[0], s, max(a.start, bt.lookback), a.window)
        print(f"{s.symbol}: {len(wins)} ventanas", flush=True)
        out["assets"][s.symbol] = analyze(s, wins, bt, a.null, a.seed,
                                          lambda m: print(m, flush=True))
    for s, path in loaded:
        s.cache.save(path)          # reutilizable en corridas posteriores
    fam = {}
    for sym, r in out["assets"].items():
        fam[f"{sym}:vs_buy_hold"] = r["buy_hold"]["p_strategy_gt_bh"]
        fam[f"{sym}:vs_random"] = r["random"]["p_sharpe"]
        fam[f"{sym}:expectancy_gt0"] = r["p_expectancy_gt0"]
    out["p_raw"], out["p_holm"] = fam, holm(fam)
    if a.fc_origins:
        print("calibración de escenarios (backfill)", flush=True)
        out["scenarios"] = scenario_calibration(series[0], 25, a.fc_origins)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    p = Path(a.out) / "edge_results.json"
    p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(p)


if __name__ == "__main__":
    main()
