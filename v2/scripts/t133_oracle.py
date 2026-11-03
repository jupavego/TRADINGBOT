"""T133 entregable 0 — cota del oráculo de M4 (E6): ¿hay techo que justifique buscar rasgos?

    python scripts/t133_oracle.py --data backups/t131_banco

Corre el banco de T131 con las dos bases (M0 escalera y M1 TP/BE+/tiempo) sobre las mismas
entradas y construye dos cotas con información que NO se conoce al entrar:

- el **oráculo por día**, con las etiquetas ex post de `ab_conditions` (M0 en lateral, M1 en
  tendencia; los días «intermedio» van a la política que se declara aquí y se informa);
- la **envolvente por operación**, la mejor de las dos salidas en cada entrada: el techo absoluto
  de cualquier selector, inalcanzable incluso con un oráculo de régimen.

Las dos se juzgan con los criterios 1–3 de §5.4 frente a M0 y frente a M1, solo con las
operaciones de los tramos de PRUEBA de los pliegues de T131 (purga y embargo incluidos). Si la
envolvente no cumple, M4 se descarta sin construir ni un rasgo.

No toca nada fuera de la copia y no abre red.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.paper.ab_conditions import LABEL_NAMES, labeler
from eim.paper.desk import PaperDesk
from eim.paper.engine import Path as PricePath
from eim.paper.exits import bench, metrics, oracle, oracle_report, run, stats
from eim.paper.exits import walkforward as wf
from eim.paper.exits.policy import ExitContext
from eim.paper.exits.prereg import load_prereg
from eim.paper.params import LADDER_BY_PROFILE, spec_for
from eim.validation.stats import rng_for

# Mapa del oráculo por día, DECLARADO aquí: los días «intermedio» y sin etiqueta van a la
# escalera, que es la salida vigente (◆1 de T129). Se informan los dos repartos.
POLICY_BY_DAY = {oracle.RANGE: "M0", oracle.TREND: "M1", oracle.MIDDLE: "M0",
                 oracle.NO_DATA: "M0"}


def fine_path(store: Store, symbol: str, tf: str) -> PricePath | None:
    if store.bounds(symbol, tf) is None:
        return None
    return PricePath.from_arrays(store.read_arrays(symbol, tf), tf_ms(tf))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="reports/t133_oracle")
    ap.add_argument("--no-fine", action="store_true")
    a = ap.parse_args()
    data = Path(a.data)
    if data.resolve() == Path("data").resolve():
        print("no se corre sobre el almacen vivo")
        return 2
    pr = load_prereg()
    sym = pr.symbol
    t0 = time.perf_counter()

    store, ps = Store(data), PaperStore(data / "paper.duckdb")
    desk = PaperDesk(store, ps, profiles=())
    v = desk.view(sym)
    if not v.outcomes or v.path is None:
        print("la copia no tiene contextos guardados")
        return 1
    fine = None if a.no_fine else fine_path(store, sym, pr.design.fine_timeframe)
    ladder = LADDER_BY_PROFILE["moderado"]
    ctx = ExitContext(path=v.path, ep=desk.ep, spec=spec_for(sym), fine=fine)

    # Solo las dos bases: la cota no necesita la rejilla entera.
    vs = [x for x in run.variants_of(pr, ladder) if x.is_base]
    ids = {x.family: x.id for x in vs}
    tfs = set(pr.design.decision_timeframes)
    ideas = [o.idea for o in v.outcomes
             if o.idea.strategy != bench.CONTROL_STRATEGY and o.idea.timeframe in tfs]
    b = bench.run(ideas, [x.policy for x in vs], ctx, pr.risk_usd)
    print(f"banco: {len(b.rows)} ideas, {len(b.paired())} emparejadas "
          f"({time.perf_counter() - t0:.0f} s)", flush=True)

    embargo = wf.embargo_for([t for x in vs for t in b.trades(x.id)],
                             feature_ms=int(pr.design.embargo_feature_hours * 3_600_000),
                             q=pr.design.embargo_quantile)
    lo, hi = wf.from_iso(pr.design.start), wf.from_iso(pr.design.end)
    if b.rows:
        lo, hi = max(lo, b.rows[0].t), min(hi, b.rows[-1].t)
    fs = wf.folds(lo, hi, embargo, pr.design.fit_months, pr.design.test_months,
                  pr.design.step_months)
    lab = labeler(v.path)

    # Las dos cotas, con el mapa traducido a los ids reales de las variantes.
    by_day = {k: ids[p] for k, p in POLICY_BY_DAY.items()}
    orc, day_counts = oracle.pick_by_day(b, lab, by_day)
    env, env_wins = oracle.pick_best(b, [ids["M0"], ids["M1"]])

    def tested(ts):
        return [t for f in fs for t in wf.test_trades(ts, f)]

    series = {ids["M0"]: tested(b.trades(ids["M0"])), ids["M1"]: tested(b.trades(ids["M1"])),
              "M4_oraculo": tested(orc), "M4_envolvente": tested(env)}
    rng = rng_for(pr.seed, f"{pr.version}|t133|ruin")
    mets = {k: metrics.summary(ts, pr.ruin.risk_pct, pr.ruin.trades, pr.ruin.reps, rng)
            for k, ts in series.items()}

    checks = {}
    for cand in ("M4_oraculo", "M4_envolvente"):
        checks[cand] = {}
        for base in (ids["M0"], ids["M1"]):
            d = oracle.diffs_vs(series[cand], series[base])
            ci = stats.paired_ci(d, pr.bootstrap.reps, pr.bootstrap.level,
                                 rng_for(pr.seed, f"{pr.version}|t133|{cand}|{base}"))
            checks[cand][base] = oracle.criteria_1_to_3(
                mets[cand], mets[base], ci, pr.accept.pf_vs_base_min,
                pr.accept.max_dd_vs_base_max)
            checks[cand][base]["n_pares"] = len(d)

    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True, check=False).stdout.strip()
    res = {
        "meta": {"data": str(data), "symbol": sym, "commit": head,
                 "built": wf.iso(int(time.time() * 1000)), "prereg": pr.version,
                 "prereg_sha256": pr.sha256, "fine_bars": 0 if fine is None else len(fine.t),
                 "seconds": round(time.perf_counter() - t0, 1)},
        "window": {"from": wf.iso(lo), "to": wf.iso(hi), "folds": len(fs),
                   "embargo_hours": round(embargo / 3_600_000, 2)},
        "bench": b.to_json(),
        "policy_by_day": {LABEL_NAMES.get(k, k): p for k, p in POLICY_BY_DAY.items()},
        "day_counts": {LABEL_NAMES.get(k, k): n for k, n in sorted(day_counts.items())},
        "envelope_wins": env_wins,
        "metrics": mets, "checks": checks, "verdict": oracle.verdict(checks),
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                   default=str), encoding="utf-8")
    out.with_suffix(".md").write_text(oracle_report.render(res), encoding="utf-8")
    print(f"\nVEREDICTO: {res['verdict']}\n")
    for k, m in mets.items():
        print(f"  {k}: n={m.get('n')} E[R]={m.get('expectancy_r')} PF={m.get('pf')} "
              f"DD={m.get('max_dd_r')} CVaR={m.get('cvar95_r')}")
    print(f"\ndatos en {out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
