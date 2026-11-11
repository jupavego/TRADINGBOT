"""T166 (descriptivo): ¿condiciona el estado de régimen el R del banco de T133?

    python scripts/t166_r_por_estado.py --data backups/t131_banco

Lee las secuencias de estados que dejó `scripts/t166_regimen.py` y las cruza con las operaciones
**fuera de muestra** del banco de T133 (base M0, la escalera vigente; solo los tramos de prueba de
sus 10 pliegues, con purga y embargo). Una operación decidida el día `d` hereda el estado del día
`d−1`, que es el último que se conoce al entrar.

Es **descriptivo y no adopta nada**: el pre-registro deja que solo la QLIKE condicional decida.
T133 descartó M4 y T134 no adoptó ninguna salida; aquí solo se mide si el estado separa el R.

No abre red y no toca el almacén vivo.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # el `eim` de este checkout

import numpy as np  # noqa: E402

from eim.data.paper_store import PaperStore  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.data.timeframes import tf_ms  # noqa: E402
from eim.paper.desk import PaperDesk  # noqa: E402
from eim.paper.engine import Path as PricePath  # noqa: E402
from eim.paper.exits import bench, run  # noqa: E402
from eim.paper.exits import walkforward as wf  # noqa: E402
from eim.paper.exits.policy import ExitContext  # noqa: E402
from eim.paper.exits.prereg import load_prereg  # noqa: E402
from eim.paper.params import LADDER_BY_PROFILE, spec_for  # noqa: E402
from eim.validation.power import n_needed, power_row  # noqa: E402
from eim.validation.stats import rng_for  # noqa: E402

REPS = 5000
SEED = 166
TARGET_R = 0.05          # el único efecto que T134 encontró (+0,0493 R): el objetivo declarado


def day_block_ci(days: np.ndarray, r: np.ndarray, group: np.ndarray, a: int, b: int,
                 reps: int = REPS) -> dict:
    """IC del ΔR medio entre dos estados por bootstrap de bloques de día (percentiles 2,5/97,5).

    Se remuestrean **días**, no operaciones: las operaciones de un mismo día están correlacionadas
    y tratarlas como independientes estrecharía el IC sin derecho.
    """
    keys = np.unique(days)
    idx = {int(k): i for i, k in enumerate(keys)}
    pos = np.array([idx[int(d)] for d in days])
    sums = np.zeros((len(keys), 2))
    cnts = np.zeros((len(keys), 2))
    for j, g in enumerate((a, b)):
        m = group == g
        np.add.at(sums[:, j], pos[m], r[m])
        np.add.at(cnts[:, j], pos[m], 1.0)
    rng = rng_for(SEED, "t166|r_por_estado")
    out = np.empty(reps)
    for i in range(reps):
        pick = rng.integers(0, len(keys), len(keys))
        s, c = sums[pick].sum(axis=0), cnts[pick].sum(axis=0)
        out[i] = (s[0] / c[0] - s[1] / c[1]) if c[0] > 0 and c[1] > 0 else np.nan
    out = out[np.isfinite(out)]
    return {"ci95": [float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))],
            "reps": int(len(out))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--states", default="reports/t166_regimen.json")
    ap.add_argument("--out", default="reports/t166_r_por_estado.json")
    a = ap.parse_args()
    data = Path(a.data)
    if data.resolve() == Path("data").resolve():
        print("no se corre sobre el almacen vivo")
        return 2
    src = json.loads(Path(a.states).read_text(encoding="utf-8"))
    days = np.asarray(src["states"]["days"], dtype=np.int64)
    by_model = {k: np.asarray(v, dtype=np.int64) for k, v in src["states"]["by_model"].items()}
    pos = {int(d): i for i, d in enumerate(days)}
    t0 = time.perf_counter()

    pr = load_prereg()
    store, ps = Store(data), PaperStore(data / "paper.duckdb")
    desk = PaperDesk(store, ps, profiles=())
    v = desk.view(pr.symbol)
    if not v.outcomes or v.path is None:
        print("la copia no tiene contextos guardados")
        return 1
    fine = None
    if store.bounds(pr.symbol, pr.design.fine_timeframe) is not None:
        fine = PricePath.from_arrays(store.read_arrays(pr.symbol, pr.design.fine_timeframe),
                                     tf_ms(pr.design.fine_timeframe))
    ctx = ExitContext(path=v.path, ep=desk.ep, spec=spec_for(pr.symbol), fine=fine)
    base = next(x for x in run.variants_of(pr, LADDER_BY_PROFILE["moderado"])
                if x.is_base and x.family == "M0")
    tfs = set(pr.design.decision_timeframes)
    ideas = [o.idea for o in v.outcomes
             if o.idea.strategy != bench.CONTROL_STRATEGY and o.idea.timeframe in tfs]
    b = bench.run(ideas, [base.policy], ctx, pr.risk_usd)
    all_trades = b.trades(base.id)
    embargo = wf.embargo_for(all_trades,
                             feature_ms=int(pr.design.embargo_feature_hours * 3_600_000),
                             q=pr.design.embargo_quantile)
    lo, hi = wf.from_iso(pr.design.start), wf.from_iso(pr.design.end)
    if b.rows:
        lo, hi = max(lo, b.rows[0].t), min(hi, b.rows[-1].t)
    folds = wf.folds(lo, hi, embargo, pr.design.fit_months, pr.design.test_months,
                     pr.design.step_months)
    tested = [t for f in folds for t in wf.test_trades(all_trades, f)]
    print(f"banco: {len(b.rows)} ideas, {len(all_trades)} operaciones, {len(tested)} fuera de "
          f"muestra ({time.perf_counter() - t0:.0f} s)", flush=True)

    t_day = np.array([t.day for t in tested], dtype=np.int64)
    t_r = np.array([t.r for t in tested], dtype=float)
    pw = power_row(list(t_r), target=TARGET_R)
    res = {"meta": {"data": f"backups/{data.name}", "states_from": a.states, "seed": SEED,
                    "reps": REPS, "prereg": "PLAN/notas/T166_preregistro.md (d5ae85e)",
                    "descriptive_only": True,
                    "command": f"python scripts/t166_r_por_estado.py --data backups/{data.name}"},
           "bench": {"ideas": len(b.rows), "trades": len(all_trades),
                     "out_of_sample": len(tested), "folds": len(folds),
                     "embargo_hours": round(embargo / 3_600_000, 2),
                     "policy": base.id, "mean_r": float(t_r.mean()) if len(t_r) else None},
           "power": {"declared_target_r": TARGET_R, "sd_r": pw.sd,
                     "n_needed": n_needed(TARGET_R, pw.sd), "n_available": len(tested),
                     "row": pw.to_json()},
           "by_model": {}}

    for name, states in by_model.items():
        if name == "U0":
            continue
        g = np.array([states[pos[int(d) - 1]] if int(d) - 1 in pos else -1 for d in t_day])
        keep = g >= 0
        groups = {}
        for s in sorted(set(int(x) for x in g[keep])):
            m = keep & (g == s)
            groups[s] = {"n": int(m.sum()), "mean_r": float(t_r[m].mean()),
                         "win_rate": float(np.mean(t_r[m] > 0)),
                         "days": int(len(np.unique(t_day[m])))}
        row = {"n_with_state": int(keep.sum()), "groups": groups}
        usable = [s for s, x in groups.items() if x["n"] >= 100]
        if len(usable) >= 2:
            best = max(usable, key=lambda s: groups[s]["mean_r"])
            worst = min(usable, key=lambda s: groups[s]["mean_r"])
            row["spread"] = {"best": best, "worst": worst,
                             "delta_mean_r": groups[best]["mean_r"] - groups[worst]["mean_r"],
                             "selected_pair": True,
                             **day_block_ci(t_day[keep], t_r[keep], g[keep], best, worst)}
        res["by_model"][name] = row
        print(f"  {name}: {row.get('spread', {}).get('delta_mean_r')}", flush=True)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"datos en {out} ({time.perf_counter() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
