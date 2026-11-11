"""T165: ¿el DVOL de Deribit mejora el pronóstico de la varianza diaria sobre el Log-HAR-RV?

    python scripts/t165_dvol.py --data <banco t139> --dvol <almacén con la serie dvol>

Familia, métricas y regla en `PLAN/notas/T165_preregistro.md` (commit 5f8ba0f, anterior a todo
resultado). La referencia a batir es M1 (Log-HAR-RV, ganador de T162), no el GARCH fijo del cono.
Escribe `reports/t165_dvol.json`; el informe en Markdown se redacta a partir de él. Va por la cola
(`eim.operation.jobs`).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # el `eim` de este checkout

import duckdb  # noqa: E402
import numpy as np  # noqa: E402

from eim.backtest.edge import holm  # noqa: E402
from eim.data.dvol import KIND, TIMEFRAME, coverage  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.forecast import vol_eval as ve  # noqa: E402
from eim.forecast import vol_models as vm  # noqa: E402
from eim.validation.lineage import iso_ms, ms_iso  # noqa: E402
from eim.validation.spa import block_length, mcs_losses, mean_diff_test  # noqa: E402

SYMBOL = "BTCUSDT"
CURRENCY = "BTC"
EVAL_FROM = "2022-01-01T00:00:00Z"
SUB_FROM = "2024-01-01T00:00:00Z"
REPS = 5000
SEED = 165
NAMES = ("M1", "A1", "A2", "A3")
Z_POWER = 2.4866  # z(0,95) + z(0,80): potencia 0,80 en el contraste unilateral al 5 %


def log(t0: float, msg: str) -> None:
    print(f"[{time.perf_counter() - t0:7.0f} s] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, help="banco de velas de 1 min (T139)")
    ap.add_argument("--dvol", required=True, help="almacén con la serie dvol de Deribit")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t0 = time.perf_counter()
    store = Store(Path(a.data))
    src = store.sql_source("candles", SYMBOL, "1m", None, None)
    m = duckdb.connect().execute(f"SELECT t, c FROM {src} ORDER BY t").fetchnumpy()
    ds = vm.daily_series(np.asarray(m["t"], np.int64), np.asarray(m["c"], float))
    del m
    days, rv, ret = ds["day"], ds["rv"], ds["ret"]
    dstore = Store(Path(a.dvol))
    hours = dstore.read_arrays(CURRENCY, TIMEFRAME, kind=KIND)
    log(t0, f"dias: {len(days)}; DVOL 1 h: {len(hours['t'])}")

    iv2 = vm.daily_implied_var(hours["t"], hours["c"], days)
    liv2 = np.log(np.where(iv2 > 0, iv2, np.nan))
    slope = vm.log_slope(iv2, 5)
    f = {"M1": vm.m1_log_har(rv)}
    log(t0, "M1 listo")
    f["A1"] = vm.log_har_x(rv, [liv2])
    f["A2"] = vm.log_har_x(rv, [liv2, slope])
    f["A3"] = 0.5 * (f["M1"] + f["A1"])
    log(t0, "A1, A2 y A3 listos")

    idx = np.arange(len(days))
    first = int(np.searchsorted(days, iso_ms(EVAL_FROM) // vm.DAY_MS))
    usable = (idx >= first) & ds["ok"] & np.isfinite(ret) & np.isfinite(iv2)
    for k in NAMES:
        usable &= np.isfinite(f[k]) & (f[k] > 0)
    sub = usable & (days >= iso_ms(SUB_FROM) // vm.DAY_MS)
    res = {
        "meta": {"symbol": SYMBOL, "currency": CURRENCY, "data": Path(a.data).name,
                 "reps": REPS, "seed": SEED, "eval_from": EVAL_FROM, "sub_from": SUB_FROM,
                 "prereg": "PLAN/notas/T165_preregistro.md (5f8ba0f)",
                 "dvol": coverage(dstore, CURRENCY),
                 "command": f"python scripts/t165_dvol.py --data {Path(a.data).name} "
                            f"--dvol {Path(a.dvol).name}"},
        "days": {"all": int(usable.sum()), "sub": int(sub.sum()),
                 "first": ms_iso(int(days[usable][0]) * vm.DAY_MS) if usable.any() else None,
                 "last": ms_iso(int(days[usable][-1]) * vm.DAY_MS) if usable.any() else None,
                 "excluded_no_dvol": int(((idx >= first) & ds["ok"] & ~np.isfinite(iv2)).sum()),
                 "excluded_low_cov": int(((idx >= first) & ~ds["ok"]).sum())},
        "vrp": vrp_summary(rv, iv2, usable),
        "coef": fit_coefficients(rv, liv2, slope, usable),
    }
    losses = np.column_stack([ve.qlike(rv[usable], f[k][usable]) for k in NAMES])
    res["block"] = block_length(losses)
    res["models"] = {k: describe(rv, ret, f[k], usable, sub) for k in NAMES}
    res["mcs"] = mcs_losses(list(NAMES), losses, 0.10, REPS, SEED)
    log(t0, f"MCS: {res['mcs']}")
    diffs, praw = {}, {}
    n = losses.shape[0]
    for j, k in enumerate(NAMES[1:], start=1):
        d = losses[:, j] - losses[:, 0]
        lo, hi, p = mean_diff_test(d, REPS, SEED)
        s = float(np.std(d, ddof=1))
        mde = Z_POWER * s / math.sqrt(n)
        diffs[k] = {"mean": float(np.mean(d)), "ci95": [lo, hi], "p_raw": p, "sd": s,
                    "mde": mde, "detectable": bool(-float(np.mean(d)) >= mde)}
        praw[k] = p
    for k, p in holm(praw).items():
        diffs[k]["p_holm"] = p
    res["vs_m1"] = diffs
    res["verdict"] = verdict(res)
    res["posthoc_control"] = control(rv, iv2, usable, f["M1"], f["A2"])
    log(t0, f"control: {res['posthoc_control']}")
    out = Path("reports/t165_dvol.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                   encoding="utf-8", newline="\n")
    log(t0, f"veredicto: {res['verdict']}")
    return 0


def control(rv: np.ndarray, iv2: np.ndarray, mask: np.ndarray, m1: np.ndarray,
            a2: np.ndarray) -> dict:
    """Control **posterior al resultado** (no decide nada; declarado como tal en el informe).

    Reconstruye A2 con el DVOL corrido un día: `lag1` usa el de ayer (información más vieja, debe
    perder algo de ventaja) y `leak` el de mañana (imposible, debe ganar mucha). Si el A2 oficial
    se pareciera al `leak`, habría fuga; si se pareciera al `lag1`, la alineación daría igual.
    """
    out = {"M1": float(ve.qlike(rv[mask], m1[mask]).mean()),
           "A2": float(ve.qlike(rv[mask], a2[mask]).mean())}
    for name, shift in (("A2_lag1", 1), ("A2_leak", -1)):
        moved = np.full(len(iv2), np.nan)
        if shift > 0:
            moved[shift:] = iv2[:-shift]
        else:
            moved[:shift] = iv2[-shift:]
        h = vm.log_har_x(rv, [np.log(np.where(moved > 0, moved, np.nan)),
                              vm.log_slope(moved, 5)])
        ok = mask & np.isfinite(h) & (h > 0)
        out[name] = float(ve.qlike(rv[ok], h[ok]).mean())
        out[f"{name}_days"] = int(ok.sum())
    return out


def vrp_summary(rv: np.ndarray, iv2: np.ndarray, mask: np.ndarray) -> dict:
    """Prima de varianza descriptiva: nivel, signo y persistencia (no decide nada)."""
    p = iv2[mask] - rv[mask]
    lr = np.log(iv2[mask] / rv[mask])
    ar1 = float(np.corrcoef(p[:-1], p[1:])[0, 1]) if len(p) > 2 else math.nan
    return {"mean": float(p.mean()), "median": float(np.median(p)),
            "positive_share": float((p > 0).mean()), "ar1": ar1,
            "mean_log_ratio": float(lr.mean()), "mean_iv2": float(iv2[mask].mean()),
            "mean_rv": float(rv[mask].mean())}


def fit_coefficients(rv: np.ndarray, liv2: np.ndarray, slope: np.ndarray,
                     mask: np.ndarray) -> dict:
    """Coeficientes de A1 y A2 ajustados de una vez sobre el tramo evaluado: solo descriptivo."""
    rows, y = [], []
    for k in np.flatnonzero(mask):
        base = vm.har_row(rv, int(k))
        if base is None or not np.isfinite([liv2[k], slope[k]]).all():
            continue
        rows.append(np.concatenate([base, [liv2[k], slope[k]]]))
        y.append(math.log(rv[k]))
    if len(rows) < 10:
        return {}
    x = np.array(rows)
    yy = np.array(y)
    names = ["c", "ln_rv_d", "ln_rv_w", "ln_rv_m", "ln_iv2", "slope5"]
    b1 = np.linalg.lstsq(x[:, :5], yy, rcond=None)[0]
    b2 = np.linalg.lstsq(x, yy, rcond=None)[0]
    return {"A1": dict(zip(names[:5], (float(v) for v in b1), strict=True)),
            "A2": dict(zip(names, (float(v) for v in b2), strict=True)), "n": len(rows)}


def describe(rv, ret, h, usable, sub) -> dict:
    out = {}
    for name, mask in (("all", usable), ("sub", sub)):
        q = ve.qlike(rv[mask], h[mask])
        raw = ve.band_hits(ret[mask], h[mask])
        out[name] = {"qlike": float(q.mean()), "mse": float(np.mean((rv[mask] - h[mask]) ** 2)),
                     "crps": float(ve.crps_normal(ret[mask], h[mask]).mean()),
                     "pit_deciles": ve.pit_deciles(ve.pit(ret[mask], h[mask])),
                     "cov80_raw": float(raw.mean()),
                     "mean_ratio": float(np.mean(rv[mask] / h[mask]))}
    # ACI se calienta con los días anteriores al tramo: se calcula sobre la serie completa
    hit = ve.aci_hits(ret, np.where(np.isfinite(h), h, np.nan))
    for name, mask in (("all", usable), ("sub", sub)):
        hm = hit[mask]
        hm = hm[np.isfinite(hm)]
        out[name]["cov80_aci"] = float(hm.mean()) if len(hm) else None
        out[name]["aci_days"] = int(len(hm))
        out[name]["aci_worst90"] = ve.worst_window(hit[mask], 0.80)
    return out


def verdict(res: dict) -> dict:
    mcs_in = {k: res["mcs"].get(k, 0.0) >= 0.10 for k in NAMES}
    out = {}
    for k in NAMES[1:]:
        d = res["vs_m1"][k]
        cov = [res["models"][k][s]["cov80_aci"] for s in ("all", "sub")]
        c1 = mcs_in[k] and not mcs_in["M1"]
        c2 = d["ci95"][1] < 0 and d["p_holm"] < 0.05
        c3 = all(c is not None and abs(c - 0.80) <= 0.02 for c in cov)
        out[k] = {"c1_mcs": c1, "c2_mejora": c2, "c3_cobertura": c3, "pasa": c1 and c2 and c3,
                  "detectable": d["detectable"]}
    passing = [k for k in NAMES[1:] if out[k]["pasa"]]
    best = min(passing, key=lambda k: res["models"][k]["all"]["qlike"]) if passing else None
    return {"by_model": out, "propuesto": best,
            "alguna_detectable": any(out[k]["detectable"] for k in NAMES[1:])}


if __name__ == "__main__":
    raise SystemExit(main())
