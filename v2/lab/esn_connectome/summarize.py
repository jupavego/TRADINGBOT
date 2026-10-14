"""Resume un JSON de `run_lab` en tablas markdown y evalúa los criterios C1–C4 del README.

Uso (desde `v2/`): `python -m lab.esn_connectome.summarize reports/esn_connectome/n500.json`
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

B = 5000
FIXED = ("cone", "base_T16", "linear")
ESN = ("esn_random", "esn_connectome", "esn_topology")


def _seed_names(cells: dict, variant: str) -> list[str]:
    return sorted(k for k in cells if k.startswith(variant + "_s"))


def _origin(asset: dict, model: str, key: str) -> np.ndarray:
    """Valores por origen; para un ESN, media de semillas (pinball/net) o primera semilla."""
    po = asset["per_origin"]
    names = _seed_names(po, model) if model in ESN else [model]
    return np.mean([np.array(po[n][key], dtype=float) for n in names], axis=0)


def _cell_pinball(asset: dict, model: str) -> np.ndarray:
    names = _seed_names(asset["cells"], model) if model in ESN else [model]
    return np.mean([[c["pinball"] for c in asset["cells"][n]] for n in names], axis=0)


def _boot_ci(x: np.ndarray, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, len(x), size=(B, len(x)))].mean(axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def compare(res: dict, a: str, b: str) -> dict:
    wins = np.concatenate([_cell_pinball(x, a) < _cell_pinball(x, b) for x in res["assets"]])
    diff = np.concatenate([_origin(x, a, "pinball") - _origin(x, b, "pinball")
                           for x in res["assets"]])
    base = np.concatenate([_origin(x, b, "pinball") for x in res["assets"]])
    lo, hi = _boot_ci(diff)
    return {"win_frac": float(wins.mean()), "cells": int(len(wins)), "diff": float(diff.mean()),
            "ci": (lo, hi), "skill": float(-diff.mean() / base.mean())}


def pooled(res: dict, model: str) -> dict:
    rows = []
    for x in res["assets"]:
        names = _seed_names(x["cells"], model) if model in ESN else [model]
        for n in names:
            po = x["per_origin"][n]
            rows.append({k: np.array(po[k], dtype=float) for k in po})
    cells = [c for x in res["assets"]
             for n in (_seed_names(x["cells"], model) if model in ESN else [model])
             for c in x["cells"][n]]
    w = np.array([1.0 for _ in cells])
    cov = {k: float(np.average([c[k] for c in cells], weights=w)) for k in ("cov50", "cov80")}
    traded = np.concatenate([r["pos"] != 0 for r in rows])
    hit = np.concatenate([r["hit"] for r in rows])[traded]
    net = np.concatenate([r["net"] for r in rows])[traded]
    pin = np.concatenate([r["pinball"] for r in rows])
    seeds = max(1, len(rows) // len(res["assets"]))
    k, n = int(hit.sum()), len(hit)
    p = binomtest(k // seeds, max(n // seeds, 1), 0.5, alternative="greater").pvalue if n else 1.0
    lo, hi = _boot_ci(net) if n else (0.0, 0.0)
    return {"pinball": float(pin.mean()), **cov, "hit": float(hit.mean()) if n else float("nan"),
            "p_dir": float(p), "net_bp": float(net.mean() * 1e4) if n else 0.0,
            "net_ci_bp": (lo * 1e4, hi * 1e4), "trades_per_seed": n // seeds}


def holm(ps: dict[str, float]) -> dict[str, float]:
    items = sorted(ps.items(), key=lambda kv: kv[1])
    out, run = {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, p * (len(items) - i)))
        out[k] = run
    return out


def report(res: dict) -> str:
    models = [m for m in FIXED + ESN if any(
        m in x["cells"] or _seed_names(x["cells"], m) for x in res["assets"])]
    pool = {m: pooled(res, m) for m in models}
    ph = holm({m: pool[m]["p_dir"] for m in models if m not in ("cone", "base_T16")})
    sg = res["subgraph"]
    out = [f"### N = {res['n']} neuronas · {res['seeds']} semillas · h = {res['horizon']} · "
           f"costo i/v {res['cost'] * 1e4:.0f} pb",
           f"Subgrafo: {sg['edges']} aristas (densidad {sg['density']:.1%}), "
           f"{sg['inhibitory_pre_frac']:.0%} presinápticas inhibidoras, "
           f"{sg['reciprocal_frac']:.0%} aristas recíprocas.", "",
           "| modelo | pinball (×1e4) | cob50 | cob80 | acierto dir. | p Holm | neto/op (pb) "
           "| IC95 neto |",
           "|---|---|---|---|---|---|---|---|"]
    for m in models:
        r = pool[m]
        pholm = f"{ph[m]:.3f}" if m in ph else "—"
        out.append(f"| {m} | {r['pinball'] * 1e4:.2f} | {r['cov50']:.1%} | {r['cov80']:.1%} | "
                   f"{r['hit']:.1%} | {pholm} | {r['net_bp']:+.1f} | "
                   f"[{r['net_ci_bp'][0]:+.1f}, {r['net_ci_bp'][1]:+.1f}] |")
    out += ["", "| comparación (pinball) | celdas ganadas | dif. media (×1e4) | IC95 | skill |",
            "|---|---|---|---|---|"]
    pairs = [("esn_connectome", "esn_random"), ("esn_connectome", "cone"),
             ("esn_connectome", "base_T16"), ("esn_connectome", "linear"),
             ("esn_topology", "esn_random"), ("esn_connectome", "esn_topology"),
             ("esn_random", "cone"), ("linear", "cone"), ("base_T16", "cone")]
    cmp = {}
    for a, b in pairs:
        if a in models and b in models:
            c = cmp[(a, b)] = compare(res, a, b)
            lo, hi = (v * 1e4 for v in c["ci"])
            out.append(f"| {a} vs {b} | {c['win_frac']:.0%} de {c['cells']} | "
                       f"{c['diff'] * 1e4:+.3f} | [{lo:+.3f}, {hi:+.3f}] | {c['skill']:+.2%} |")
    out += ["", criteria(cmp, pool, ph)]
    return "\n".join(out)


def criteria(cmp: dict, pool: dict, ph: dict) -> str:
    def ok(a: str, b: str) -> bool:
        c = cmp.get((a, b))
        return bool(c and c["win_frac"] >= 0.75 and c["ci"][1] < 0)

    r = pool.get("esn_connectome")
    c1 = ok("esn_connectome", "esn_random")
    c2 = ok("esn_connectome", "cone") and ok("esn_connectome", "base_T16")
    c3 = bool(r and 0.75 <= r["cov80"] <= 0.85 and 0.45 <= r["cov50"] <= 0.55)
    c4 = bool(r and ph.get("esn_connectome", 1) < 0.05 and r["net_ci_bp"][0] > 0)
    yn = {True: "sí", False: "no"}
    win = c1 and c2 and c3
    return (f"Criterios: C1 {yn[c1]} · C2 {yn[c2]} · C3 {yn[c3]} · C4 {yn[c4]} → "
            f"**{'GANA' if win else 'NO GANA'}**")


def main() -> None:  # pragma: no cover
    for p in sys.argv[1:]:
        print(report(json.loads(Path(p).read_text(encoding="utf-8"))))
        print()


if __name__ == "__main__":  # pragma: no cover
    main()
