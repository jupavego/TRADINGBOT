"""Marco fuera de muestra de T80 (b) y (c): IC, pb netos y Holm sobre todos los intentos. Puro.

Cada señal (las 15 variables, la línea base v1 y la ridge conjunta) se convierte en una
**predicción en pb** con un ajuste lineal hecho SOLO con los días de entrenamiento del pliegue;
así todas se comparan en la misma unidad y el signo lo pone el entrenamiento, no el resultado.

Por pliegue (walk-forward por días, con purga y embargo) y por señal se guardan dos cosas del día
de prueba: su IC de Spearman y, por estilo de ejecución, los pb netos medios de las filas en las
que la predicción supera el costo. Después se agregan por día con bootstrap de bloques de día, se
calcula la p unilateral de media > 0 y se corrige por Holm sobre la familia completa declarada en
el pre-registro.

Aviso que va al informe: a horizonte h y cubos de 1 s las operaciones se solapan (una por cubo),
así que el número de operaciones NO es realizable; el equivalente sin solape es filas / (h/paso).
Las medias por día y sus IC por bloques de día sí son legítimos.
"""

from __future__ import annotations

import math

import numpy as np

from eim.backtest.edge import holm, perm_pvalue
from eim.hft.evaluation import metrics as M
from eim.hft.evaluation import ridge as R
from eim.hft.evaluation.splits import Fold, day_of, fold_masks
from eim.validation.stats import rng_for

RIDGE = "ridge_all"
UNI_ALPHA = 1e-6          # ajuste lineal de una variable: ridge con penalización simbólica


def fit_predict(x_tr: np.ndarray, y_tr: np.ndarray, x_te: np.ndarray,
                multi: bool) -> np.ndarray:
    """Predicción en pb del día de prueba, con el modelo ajustado solo en el entrenamiento."""
    model = R.fit_cv(x_tr, y_tr) if multi else R.fit(x_tr, y_tr, UNI_ALPHA)
    return model.predict(x_te)


TOP_FRAC = 0.1            # decil de |predicción| más alta: operación selectiva sin umbral de pb


def gross_bps(pred: np.ndarray, y: np.ndarray, frac: float | None = None) -> float:
    """pb BRUTOS por operación (sin costo): media de signo(predicción) × Δmid.

    Con `frac`, solo el `frac` de filas con |predicción| más alta (operación selectiva).
    """
    p, yy = np.asarray(pred, float), np.asarray(y, float)
    ok = np.isfinite(p) & np.isfinite(yy)
    if not ok.any():
        return math.nan
    p, yy = p[ok], yy[ok]
    if frac is not None:
        k = max(int(p.size * frac), 1)
        sel = np.argpartition(-np.abs(p), k - 1)[:k]
        p, yy = p[sel], yy[sel]
    return float((np.sign(p) * yy).mean())


def fold_signal(pred: np.ndarray, y: np.ndarray, costs: dict[str, float]) -> dict:
    """IC del día, pb brutos y pb netos por estilo (solo donde la predicción supera el costo)."""
    row: dict = {"ic": M.spearman(pred, y), "rows": int(pred.size),
                 "gross": gross_bps(pred, y),
                 "gross_top": gross_bps(pred, y, TOP_FRAC), "net": {}}
    for name, c in costs.items():
        net, take = M.net_bps(pred, y, c, threshold=c)
        row["net"][name] = {"mean": float(net.mean()) if net.size else math.nan,
                            "n": int(net.size), "share": float(take.mean()) if take.size else 0.0}
    return row


def run_horizon(t: np.ndarray, x: np.ndarray, names: tuple[str, ...], y: np.ndarray,
                folds: list[Fold], horizon_ms: int, costs: dict[str, float]) -> dict:
    """Walk-forward de un horizonte: devuelve, por señal, la serie de días de prueba."""
    out = {n: {"days": [], "ic": [], "gross": [], "gross_top": [],
               "net": {k: {"mean": [], "n": [], "share": []} for k in costs}}
           for n in (*names, RIDGE)}
    for fold in folds:
        tr, te = fold_masks(t, fold, horizon_ms)
        if tr.sum() < 1000 or te.sum() < 1000:
            continue
        day = int(day_of(t[te])[0])
        x_tr, y_tr, x_te, y_te = x[tr], y[tr], x[te], y[te]
        for j, name in enumerate(names):
            pred = fit_predict(x_tr[:, [j]], y_tr, x_te[:, [j]], multi=False)
            _store(out[name], day, fold_signal(pred, y_te, costs), costs)
        pred = fit_predict(x_tr, y_tr, x_te, multi=True)
        _store(out[RIDGE], day, fold_signal(pred, y_te, costs), costs)
    return out


def _store(acc: dict, day: int, row: dict, costs: dict[str, float]) -> None:
    acc["days"].append(day)
    acc["ic"].append(row["ic"])
    acc["gross"].append(row["gross"])
    acc["gross_top"].append(row["gross_top"])
    for k in costs:
        for field in ("mean", "n", "share"):
            acc["net"][k][field].append(row["net"][k][field])


def day_pvalue(values: np.ndarray, reps: int, seed: int, label: str) -> float:
    """p unilateral de media > 0 remuestreando DÍAS con la muestra recentrada en 0."""
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if v.size < 3:
        return 1.0
    rng = rng_for(seed, label)
    z = v - v.mean()
    boots = z[rng.integers(0, v.size, size=(reps, v.size))].mean(axis=1)
    return perm_pvalue(float(v.mean()), boots)


def summarize_signal(acc: dict, costs: dict[str, float], reps: int, level: float,
                     seed: int, label: str) -> dict:
    """Media por día con IC, p unilateral y pb netos por estilo de una señal y horizonte."""
    days = np.asarray(acc["days"], dtype=np.int64)
    ic = np.asarray(acc["ic"], float)
    ok = np.isfinite(ic)
    res = {"test_days": int(ok.sum()),
           "ic": M.mean_ci(ic[ok], days[ok], reps, level, f"{label}|ic", seed),
           "ic_p": day_pvalue(ic[ok], reps, seed, f"{label}|ic"), "net": {}}
    for key in ("gross", "gross_top"):
        v = np.asarray(acc[key], float)
        good = np.isfinite(v)
        res[key] = (M.mean_ci(v[good], days[good], reps, level, f"{label}|{key}", seed)
                    if good.any() else {"n_days": 0, "mean": None, "lo": None, "hi": None})
    for name in costs:
        mean = np.asarray(acc["net"][name]["mean"], float)
        n = np.asarray(acc["net"][name]["n"], float)
        share = np.asarray(acc["net"][name]["share"], float)
        good = np.isfinite(mean) & (n > 0)
        row = {"days": int(good.sum()), "trades": int(n.sum()),
               "share_of_rows": round(float(share[good].mean()), 5) if good.any() else 0.0}
        if good.any():
            row |= M.mean_ci(mean[good], days[good], reps, level, f"{label}|{name}", seed)
            row["p"] = day_pvalue(mean[good], reps, seed, f"{label}|{name}")
        res["net"][name] = row
    return res


def evaluate(t: np.ndarray, x: np.ndarray, names: tuple[str, ...], labels: dict[int, np.ndarray],
             folds_by_h: dict[int, list[Fold]], costs: dict[str, float], reps: int,
             level: float, seed: int, step_ms: int) -> dict:
    """Todos los horizontes y señales, con Holm sobre la familia completa de intentos.

    `labels[h]` es el Δmid del horizonte `h` (en pb, con la reacción ya aplicada) para las
    MISMAS filas de `t` y `x`.
    """
    per_h: dict[str, dict] = {}
    pvals: dict[str, float] = {}
    for h, y in labels.items():
        raw = run_horizon(t, x, names, y, folds_by_h[h], h * 1000, costs)
        block = {}
        for name, acc in raw.items():
            label = f"{name}@{h}s"
            s = summarize_signal(acc, costs, reps, level, seed, label)
            s["overlap"] = max(1, (h * 1000) // step_ms)
            block[name] = s
            pvals[label] = s["ic_p"]
        per_h[str(h)] = block
    adj = holm(pvals)
    for h, block in per_h.items():
        for name, s in block.items():
            s["ic_p_holm"] = adj[f"{name}@{h}s"]
    return {"attempts": len(pvals), "holm": adj, "horizons": per_h}
