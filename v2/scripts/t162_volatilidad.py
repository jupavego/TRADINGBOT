"""T162: volatilidad del día siguiente para el cono, según el pre-registro.

    python scripts/t162_volatilidad.py --data backups/t139_banco

Regla, familia y métricas en `PLAN/notas/T162_preregistro.md` (commit ebaae60, anterior a todo
resultado). Escribe `reports/t162_cono_volatilidad.json`; el informe en Markdown se redacta a
partir de él. Va por la cola (`eim.operation.jobs`).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # el `eim` de este checkout

import duckdb  # noqa: E402
import numpy as np  # noqa: E402

from eim.backtest.edge import holm  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.forecast import vol_eval as ve  # noqa: E402
from eim.forecast import vol_models as vm  # noqa: E402
from eim.validation.lineage import iso_ms  # noqa: E402
from eim.validation.spa import block_length, mcs_losses, mean_diff_test  # noqa: E402

SYMBOL = "BTCUSDT"
EVAL_FROM = "2021-01-01T00:00:00Z"
SUB_FROM = "2024-01-01T00:00:00Z"
REPS = 5000
SEED = 162
NAMES = ("M0", "M1", "M2", "M3")


def log(t0: float, msg: str) -> None:
    print(f"[{time.perf_counter() - t0:7.0f} s] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t0 = time.perf_counter()
    store = Store(Path(a.data))
    src = store.sql_source("candles", SYMBOL, "1m", None, None)
    m = duckdb.connect().execute(f"SELECT t, c FROM {src} ORDER BY t").fetchnumpy()
    hours = store.read_arrays(SYMBOL, "1h")
    log(t0, f"1 min: {len(m['t'])}; 1 h: {len(hours['t'])}")
    ds = vm.daily_series(np.asarray(m["t"], np.int64), np.asarray(m["c"], float))
    del m
    days, rv, ret = ds["day"], ds["rv"], ds["ret"]
    first = int(np.searchsorted(days, iso_ms(EVAL_FROM) // vm.DAY_MS))
    f = {"M0": vm.m0_fixed_garch(hours["t"], hours["c"], days)}
    log(t0, "M0 listo")
    f["M1"] = vm.m1_log_har(rv)
    log(t0, "M1 listo")
    f["M2"] = vm.m2_gjr_garch(ret, first)
    log(t0, "M2 listo")
    f["M3"] = 0.5 * (f["M1"] + f["M2"])
    idx = np.arange(len(days))
    usable = (idx >= first) & ds["ok"] & np.isfinite(ret)
    for k in NAMES:
        usable &= np.isfinite(f[k]) & (f[k] > 0)
    sub = usable & (days >= iso_ms(SUB_FROM) // vm.DAY_MS)
    res = {"meta": {"symbol": SYMBOL, "data": f"backups/{Path(a.data).name}", "reps": REPS,
                    "seed": SEED, "eval_from": EVAL_FROM, "sub_from": SUB_FROM,
                    "prereg": "PLAN/notas/T162_preregistro.md (ebaae60)",
                    "command": f"python scripts/t162_volatilidad.py --data backups/"
                               f"{Path(a.data).name}"},
           "days": {"all": int(usable.sum()), "sub": int(sub.sum()),
                    "excluded_low_cov": int(((idx >= first) & ~ds["ok"]).sum())}}
    losses = np.column_stack([ve.qlike(rv[usable], f[k][usable]) for k in NAMES])
    res["block"] = block_length(losses)
    res["models"] = {k: describe(rv, ret, f[k], usable, sub) for k in NAMES}
    res["mcs"] = mcs_losses(list(NAMES), losses, 0.10, REPS, SEED)
    log(t0, f"MCS: {res['mcs']}")
    diffs, praw = {}, {}
    for j, k in enumerate(NAMES[1:], start=1):
        lo, hi, p = mean_diff_test(losses[:, j] - losses[:, 0], REPS, SEED)
        diffs[k] = {"mean": float(np.mean(losses[:, j] - losses[:, 0])), "ci95": [lo, hi],
                    "p_raw": p}
        praw[k] = p
    for k, p in holm(praw).items():
        diffs[k]["p_holm"] = p
    res["vs_m0"] = diffs
    res["verdict"] = verdict(res)
    out = Path("reports/t162_cono_volatilidad.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                   encoding="utf-8", newline="\n")
    log(t0, f"veredicto: {res['verdict']}")
    return 0


def describe(rv, ret, h, usable, sub) -> dict:
    out = {}
    for name, mask in (("all", usable), ("sub", sub)):
        q = ve.qlike(rv[mask], h[mask])
        raw = ve.band_hits(ret[mask], h[mask])
        out[name] = {"qlike": float(q.mean()), "mse": float(np.mean((rv[mask] - h[mask]) ** 2)),
                     "crps": float(ve.crps_normal(ret[mask], h[mask]).mean()),
                     "pit_deciles": ve.pit_deciles(ve.pit(ret[mask], h[mask])),
                     "cov80_raw": float(raw.mean()), "mean_ratio": float(np.mean(rv[mask] /
                                                                               h[mask]))}
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
        d = res["vs_m0"][k]
        cov = [res["models"][k][s]["cov80_aci"] for s in ("all", "sub")]
        c1 = mcs_in[k] and not mcs_in["M0"]
        c2 = d["ci95"][1] < 0 and d["p_holm"] < 0.05
        c3 = all(c is not None and abs(c - 0.80) <= 0.02 for c in cov)
        out[k] = {"c1_mcs": c1, "c2_mejora": c2, "c3_cobertura": c3, "pasa": c1 and c2 and c3}
    passing = [k for k in NAMES[1:] if out[k]["pasa"]]
    best = min(passing, key=lambda k: res["models"][k]["all"]["qlike"]) if passing else None
    return {"by_model": out, "propuesto": best}


if __name__ == "__main__":
    raise SystemExit(main())
