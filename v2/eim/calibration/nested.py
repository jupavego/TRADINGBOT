"""Validación anidada: optimizar en entrenamiento, evaluar SOLO en la ventana posterior.

Pliegues externos que avanzan `test` velas: entrenamiento `[s, s+train)` (partido en `inner`
subventanas para el objetivo por ventana) y prueba `[s+train, s+train+test)` nunca vista por la
búsqueda. Control cruzado: los parámetros de cada pliegue se aplican, sin reoptimizar, a la
misma ventana temporal de otro símbolo. Todos los cortes se alinean a `align` velas para que las
decisiones caigan en las mismas velas del caché de insumos.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable

from eim.backtest.params import BacktestParams
from eim.calibration.evaluate import (
    DEFAULT_OBJECTIVE,
    Evaluation,
    ObjectiveParams,
    Series,
    evaluate,
    pooled_metrics,
    run_window,
    score_of,
)
from eim.calibration.search import optimize
from eim.calibration.space import defaults


def outer_folds(n: int, start: int, train: int, test: int, inner: int,
                align: int = 6) -> list[dict]:
    start += -start % align
    sub = (train // inner) // align * align
    train = sub * inner
    test = test // align * align
    out, s = [], start
    while s + train + test <= n:
        out.append({"train": [(s + k * sub, s + (k + 1) * sub) for k in range(inner)],
                    "test": [(s + train, s + train + test)]})
        s += test
    return out


def _map(series: Series, other: Series, windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Mismas fechas en otra serie (por tiempo de apertura); omite ventanas sin cobertura."""
    idx = {c.t: i for i, c in enumerate(other.candles)}
    out = []
    for a, b in windows:
        ia, ib = idx.get(series.candles[a].t), idx.get(series.candles[b - 1].t)
        if ia is not None and ib is not None and ib - ia == b - 1 - a:
            out.append((ia, ib + 1))
    return out


def _merge(evs: list[Evaluation], values: dict, base: dict, op: ObjectiveParams) -> Evaluation:
    m = Evaluation()
    for e in evs:
        m.windows += e.windows
        m.results += e.results
    m.median_sharpe = statistics.median(w["sharpe"] for w in m.windows) if m.windows else 0.0
    m.worst_dd = max((w["max_drawdown"] for w in m.windows), default=0.0)
    m.n_trades = sum(w["n_trades"] for w in m.windows)
    m.score = score_of(m, values, base, op)
    return m


def run_nested(main: Series, control: Series | None, bt: BacktestParams, *, train: int,
               test: int, inner: int = 3, start: int = 504, n_trials: int = 40, top_k: int = 3,
               seed: int = 0, op: ObjectiveParams = DEFAULT_OBJECTIVE,
               log: Callable[[str], None] = print) -> dict:
    base = defaults()
    folds = outer_folds(len(main.candles), max(start, bt.lookback), train, test, inner)
    if not folds:
        raise ValueError("serie demasiado corta para un pliegue de entrenamiento + prueba")
    out_folds = []
    oos = {"default": [], "calibrated": []}
    ctl = {"default": [], "calibrated": []}
    for k, f in enumerate(folds):
        log(f"pliegue {k + 1}/{len(folds)}: optimizando {n_trials} trials")
        sr = optimize(main, f["train"], bt, base, op, n_trials, top_k, seed + k)
        tr_d = evaluate(main, base, f["train"], bt, base, op)
        tr_c = evaluate(main, sr.values, f["train"], bt, base, op)
        te_d = evaluate(main, base, f["test"], bt, base, op)
        te_c = evaluate(main, sr.values, f["test"], bt, base, op)
        oos["default"].append(te_d)
        oos["calibrated"].append(te_c)
        fold = {"train_from_t": main.candles[f["train"][0][0]].t,
                "test_from_t": main.candles[f["test"][0][0]].t,
                "test_to_t": main.candles[f["test"][0][1] - 1].t,
                "values": sr.values, "kept_default": sr.kept_default, "n_trials": sr.n_trials,
                "candidates": sr.candidates,
                "stability": None if sr.stability is None else {
                    "worst": sr.stability.worst, "worst_label": sr.stability.worst_label,
                    "peaked": sr.stability.peaked, "drops": sr.stability.drops},
                "train": {"default": _brief(tr_d), "calibrated": _brief(tr_c)},
                "test": {"default": _brief(te_d), "calibrated": _brief(te_c)}}
        if control is not None:
            cw = _map(main, control, f["test"])
            if cw:
                c_d = evaluate(control, base, cw, bt, base, op)
                c_c = evaluate(control, sr.values, cw, bt, base, op)
                ctl["default"].append(c_d)
                ctl["calibrated"].append(c_c)
                fold["control"] = {"default": _brief(c_d), "calibrated": _brief(c_c)}
        log(f"  entrenamiento {tr_d.score:+.2f} -> {tr_c.score:+.2f} | "
            f"prueba {te_d.score:+.2f} -> {te_c.score:+.2f}")
        out_folds.append(fold)
    agg = {"oos": {s: pooled_metrics(_merge(oos[s], base, base, op), bt) for s in oos}}
    if ctl["default"]:
        agg["control"] = {s: pooled_metrics(_merge(ctl[s], base, base, op), bt) for s in ctl}
    return {"base": base, "folds": out_folds, "aggregate": agg,
            "decision": decide(out_folds, agg)}


def _brief(e: Evaluation) -> dict:
    return {"score": e.score, "median_sharpe": e.median_sharpe, "worst_dd": e.worst_dd,
            "n_trades": e.n_trades, "windows": e.windows}


def decide(folds: list[dict], agg: dict) -> dict:
    """Se aceptan los parámetros del último pliegue solo si el PROCEDIMIENTO mejora fuera de
    muestra (mediana de Sharpe por ventana), no empeora el control cruzado, y la solución final
    no es la vigente ni es picuda. Si no, se declara y se mantienen los valores previos."""
    o, reasons = agg["oos"], []
    if o["calibrated"]["median_window_sharpe"] <= o["default"]["median_window_sharpe"]:
        reasons.append("la mediana de Sharpe fuera de muestra no mejora a la vigente")
    wins = sum(f["test"]["calibrated"]["median_sharpe"] > f["test"]["default"]["median_sharpe"]
               for f in folds)
    if wins * 2 <= len(folds):
        reasons.append(f"la calibración gana solo en {wins} de {len(folds)} pliegues de prueba")
    c = agg.get("control")
    if c and c["calibrated"]["median_window_sharpe"] < c["default"]["median_window_sharpe"]:
        reasons.append("empeora el control cruzado (otro símbolo)")
    if folds[-1]["kept_default"]:
        reasons.append("en el último pliegue ningún candidato superó de forma estable al vigente")
    return {"accepted": not reasons, "fold_wins": wins, "reasons": reasons}


def fidelity(series: Series, values: dict, window: tuple[int, int], bt: BacktestParams) -> dict:
    """Concordancia entre el caché de insumos y el agente de plan completo en una ventana."""
    a, b = window
    rc = run_window(series, values, a, b, bt, cached=True)
    rf = run_window(series, values, a, b, bt, cached=False)
    ec, ef = {t.entry_t for t in rc.trades}, {t.entry_t for t in rf.trades}
    return {"bars": b - a, "trades_cached": len(rc.trades), "trades_full": len(rf.trades),
            "same_entries": len(ec & ef),
            "return_cached": rc.equity[-1] / bt.initial_equity - 1 if rc.equity else 0.0,
            "return_full": rf.equity[-1] / bt.initial_equity - 1 if rf.equity else 0.0}
