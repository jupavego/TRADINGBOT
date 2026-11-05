"""T136 — riesgo por operación con costos, frenos graduales y tamaño: lo que dice el banco.

    python scripts/t136_riesgo.py --data backups/t131_banco

Mide sobre el banco de T131, con la salida VIGENTE (la escalera) y solo con los tramos de prueba
de los pliegues de T134 (purga y embargo incluidos), las cinco cosas que T136 pide:

1. el costo que el riesgo por operación no incluye, y cuánto se pasa hoy de lo declarado;
2. el tope de costo en R de la rejilla de §4.5, con el costo **ex ante**, que es el que veta;
3. los frenos de la rejilla pre-registrada de S3 (todo o nada frente a gradual) y el límite de
   CVaR, simulando el capital del perfil con los MISMOS `caps` que corren en el libro;
4. el Kelly fraccionado sobre el límite inferior del IC de E[R] (E10): el tamaño que saldría hoy;
5. la comprobación del ES de Acerbi y Székely por pliegue (E12), y el tamaño por volatilidad
   objetivo con la σ versionada de T132 (entregable 3, opcional).

No toca nada fuera de la copia, no abre red y no habilita dinero real.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import numpy as np

from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.paper import risk_budget
from eim.paper.desk import PaperDesk
from eim.paper.engine import Path as PricePath
from eim.paper.exits import bench, es_check, features, metrics, risk_report, risk_study, run
from eim.paper.exits import walkforward as wf
from eim.paper.exits.policy import ExitContext
from eim.paper.exits.prereg import load_prereg
from eim.paper.kelly import KellyParams
from eim.paper.params import LADDER_BY_PROFILE, PROFILES, ExecParams, spec_for
from eim.validation.stats import rng_for

COST_CAPS = (0.08, 0.10, 0.12, 0.15, 0.20)   # rejilla de §4.5 + los tres topes de hoy
SIGMA_FOR_SIZE = "harrv_1m"                  # la misma σ versionada que el stop (E11)


def fine_path(store: Store, symbol: str, tf: str) -> PricePath | None:
    if store.bounds(symbol, tf) is None:
        return None
    return PricePath.from_arrays(store.read_arrays(symbol, tf), tf_ms(tf))


def sigma_by_trade(path: PricePath, feats: features.ExitFeatures,
                   trades) -> dict[str, float]:
    """σ RELATIVA en la vela del llenado de cada operación (fracción del precio)."""
    rel = np.where((path.c > 0) & np.isfinite(path.c), feats.sigma_abs / path.c, np.nan)
    out = {}
    for t in trades:
        j = int(np.searchsorted(path.t, t.fill_t, side="right")) - 1
        if 0 <= j < len(rel) and np.isfinite(rel[j]):
            out[t.id] = float(rel[j])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="", help="copia con el banco de T131")
    ap.add_argument("--out", default="reports/t136_riesgo")
    ap.add_argument("--no-fine", action="store_true")
    ap.add_argument("--from-json", default="",
                    help="solo vuelve a escribir el informe desde un JSON ya calculado")
    a = ap.parse_args()
    if a.from_json:
        res = json.loads(Path(a.from_json).read_text(encoding="utf-8"))
        Path(a.out).with_suffix(".md").write_text(risk_report.render(res), encoding="utf-8")
        print(f"informe reescrito desde {a.from_json}")
        return 0
    if not a.data:
        print("hace falta --data (la copia con el banco de T131) o --from-json")
        return 2
    data = Path(a.data)
    if data.resolve() == Path("data").resolve():
        print("no se corre sobre el almacen vivo")
        return 2
    pr = load_prereg()
    sym, t0 = pr.symbol, time.perf_counter()

    store, ps = Store(data), PaperStore(data / "paper.duckdb")
    desk = PaperDesk(store, ps, profiles=())
    v = desk.view(sym)
    if not v.outcomes or v.path is None:
        print("la copia no tiene contextos guardados")
        return 1
    fine = None if a.no_fine else fine_path(store, sym, pr.design.fine_timeframe)
    ctx = ExitContext(path=v.path, ep=desk.ep, spec=spec_for(sym), fine=fine)

    # la salida VIGENTE, nada más: T136 no elige salidas (eso lo cerró T134)
    base = next(x for x in run.variants_of(pr, LADDER_BY_PROFILE["moderado"])
                if x.is_base and x.family == "M0")
    tfs = set(pr.design.decision_timeframes)
    ideas = [o.idea for o in v.outcomes
             if o.idea.strategy != bench.CONTROL_STRATEGY and o.idea.timeframe in tfs]
    b = bench.run(ideas, [base.policy], ctx, pr.risk_usd)
    all_trades = b.trades(base.id)
    print(f"banco: {len(b.rows)} ideas, {len(all_trades)} cerradas "
          f"({time.perf_counter() - t0:.0f} s)", flush=True)

    embargo = wf.embargo_for(all_trades,
                            feature_ms=int(pr.design.embargo_feature_hours * 3_600_000),
                            q=pr.design.embargo_quantile)
    lo, hi = wf.from_iso(pr.design.start), wf.from_iso(pr.design.end)
    if b.rows:
        lo, hi = max(lo, b.rows[0].t), min(hi, b.rows[-1].t)
    fs = wf.folds(lo, hi, embargo, pr.design.fit_months, pr.design.test_months,
                  pr.design.step_months)
    by_fold = [wf.test_trades(all_trades, f) for f in fs]
    tested = [t for g in by_fold for t in g]
    print(f"pliegues: {len(fs)}, fuera de muestra: {len(tested)} operaciones", flush=True)

    # costo EX ANTE por idea: el que el perfil estima al decidir y con el que veta
    ec = ExecParams().est_cost_frac
    ex_ante = {i.id: risk_budget.cost_r(i.entry, i.sl, ec) for i in ideas}

    # σ versionada para el tamaño por volatilidad objetivo (entregable 3, opcional)
    feats = features.build(v.path, SIGMA_FOR_SIZE, fine=fine)
    sig = sigma_by_trade(v.path, feats, tested)

    s3 = pr.item("S3").params
    risk_pct = {p.id: p.risk_pct for p in PROFILES}
    rng = rng_for(pr.seed, f"{pr.version}|t136|es")
    es_folds = []
    for n, f in enumerate(fs):
        fit = wf.fit_trades(all_trades, f)      # ya con purga y embargo (E1)
        test = wf.test_trades(all_trades, f)
        if not fit or not test:
            continue
        out = es_check.check(np.array([t.day for t in fit]), np.array([t.r for t in fit]),
                             np.array([t.day for t in test]), np.array([t.r for t in test]),
                             pr.bootstrap.reps, rng)
        es_folds.append({"fold": n, "test_from": wf.iso(f.test_from), **out})

    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True, check=False).stdout.strip()
    res = {
        "meta": {"data": str(data), "symbol": sym, "commit": head,
                 "built": wf.iso(int(time.time() * 1000)), "prereg": pr.version,
                 "prereg_sha256": pr.sha256, "policy": base.id,
                 "est_cost_frac": ec, "sigma": SIGMA_FOR_SIZE,
                 "fine_bars": 0 if fine is None else len(fine.t),
                 "seconds": round(time.perf_counter() - t0, 1)},
        "window": {"from": wf.iso(lo), "to": wf.iso(hi), "folds": len(fs),
                   "embargo_hours": round(embargo / 3_600_000, 2),
                   "n_closed": len(all_trades), "n_tested": len(tested)},
        "metrics": metrics.summary(tested),
        "costs": risk_study.cost_profile(tested, ex_ante),
        "cost_caps": risk_study.cost_cap_grid(tested, ex_ante, COST_CAPS),
        "profiles_today": {p.id: {"risk_pct": p.risk_pct, "max_cost_r": p.max_cost_r,
                                  "risk_includes_costs": p.risk_includes_costs,
                                  "dd_brake": p.caps.dd_brake,
                                  "dd_steps": list(p.caps.dd_steps),
                                  "cvar_limit_r": p.caps.cvar_limit_r} for p in PROFILES},
        "brakes": {pid: risk_study.brake_grid(tested, pct, tuple(s3["dd_brake"]),
                                              tuple(s3["cvar_limit_r"]))
                   for pid, pct in risk_pct.items()},
        "brakes_by_fold": {pid: risk_study.brake_grid_by_fold(
            by_fold, pct, tuple(s3["dd_brake"]), tuple(s3["cvar_limit_r"]))
            for pid, pct in risk_pct.items()},
        "kelly": risk_study.kelly_view(tested, KellyParams(), risk_pct),
        "vol_target": risk_study.vol_target_view(tested, sig, tuple(s3["vol_target"])),
        "sigma_coverage": feats.to_json(),
        "es": es_folds,
        "prereg_s3": s3,
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                   default=str), encoding="utf-8")
    out.with_suffix(".md").write_text(risk_report.render(res), encoding="utf-8")
    c = res["costs"]
    print(f"\ncosto ex ante medio {c['cost_r_ex_ante']['mean']:.4f} R -> hoy se arriesga "
          f"x{c['risk_overrun']:.4f} lo declarado")
    print(f"Kelly: E[R] {res['kelly']['mean_r']:+.4f}, limite inferior "
          f"{res['kelly']['lower_r']:+.4f} -> tamano "
          f"{max(res['kelly']['risk_pct'].values()):.4%}")
    print(f"\ndatos en {out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
