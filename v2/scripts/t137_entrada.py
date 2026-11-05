"""T137 — versiones de entrada con SL más amplio y tope de costo, por la puerta de T49.

    python scripts/t137_entrada.py --data backups/t131_banco            # corrida completa
    python scripts/t137_entrada.py --data backups/t131_banco --sample-only   # solo cuenta muestra

Aplica `prereg_t137_v1` tal cual y escribe `reports/t137_entrada.{md,json,csv}` y
`eim/validation/attempts_t137.json`. Abre una COPIA temporal del `paper.duckdb` del banco: no toca
el almacén vivo ni el banco, no abre red y no habilita dinero real.
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.data.validation_store import ValidationStore
from eim.paper.catalog import CATALOG, generate_ideas
from eim.paper.desk import WARMUP_BARS, PaperDesk
from eim.paper.engine import FUNDING_MS, run_shadow
from eim.paper.engine import Path as PricePath
from eim.paper.exits import bench, features
from eim.paper.exits import walkforward as wf
from eim.paper.exits.policy import ExitContext, ShadowExit
from eim.paper.exits.prereg import load_prereg as load_t131
from eim.paper.params import LADDER_BY_PROFILE, spec_for
from eim.validation import entry_control as ec
from eim.validation import entry_report as er
from eim.validation import entry_run as run
from eim.validation import entry_versions as ev
from eim.validation.attempts import ATTEMPTS_FILE, write_attempts
from eim.validation.criteria import load_criteria
from eim.validation.entry_prereg import load_prereg
from eim.validation.lineage import iso_ms
from eim.validation.service import summarize

PREREG_COMMIT = "213247f"


def log(t0: float, msg: str) -> None:
    print(f"[{time.perf_counter() - t0:7.0f} s] {msg}", flush=True)


def load_world(store: Store, ps: PaperStore, desk: PaperDesk, sym: str):
    """Las ideas de TODAS las reglas vigentes y el camino, igual que `PaperDesk._compute`."""
    ep = desk.ep
    ideas, firsts = [], []
    for tf in desk.tfs:
        ctxs = ps.load(sym, tf)
        if not ctxs:
            continue
        firsts.append(ctxs[0]["t"])
        bar = tf_ms(tf)
        candles = store.read_candles(sym, tf, start=ctxs[0]["t"] - WARMUP_BARS * bar)
        ideas += generate_ideas(ctxs, candles, sym, bar, timeframe=tf,
                                htf=desk._htf(sym, tf, ctxs[0]["t"]), exec_params=ep)
        del ctxs, candles
        gc.collect()
    t0 = min(firsts)
    pc = store.read_candles(sym, ep.path_tf, start=t0 - tf_ms("4h"))
    funding = store.read_series("funding", sym, start=t0 - FUNDING_MS)
    return ideas, PricePath(pc, funding, tf_ms(ep.path_tf))


def published(reports: Path) -> dict:
    """Las cifras ya publicadas por T134 y T136 que la regresión tiene que reproducir."""
    t134 = json.loads((reports / "exits_ab.json").read_text(encoding="utf-8"))["metrics"]
    t136 = json.loads((reports / "t136_riesgo.json").read_text(encoding="utf-8"))
    pick = {k: t134[k]["test"] for k in ("M0 first_r=0.1", "M8 q=0.95",
                                         "S1 d_min_sigma=3 sigma=atr14")}
    return {**pick, "cap": next(x for x in t136["cost_caps"] if x["cap_r"] == 0.08)}


def say_sample(sample: dict) -> None:
    for rid, s in sample.items():
        print(f"\n== {rid}: versiones que llegan a V1 por variante: {s['meets_v1']} "
              f"de {s['versions']}")
        for vid, by_tf in s["pooled"].items():
            bits = [f"{tf} n={x['n']}" for tf, x in by_tf.items()]
            print(f"  {vid:<8} " + " · ".join(bits))


def main() -> int:  # noqa: PLR0915
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="reports/t137_entrada")
    ap.add_argument("--sample-only", action="store_true")
    ap.add_argument("--no-regression", action="store_true")
    ap.add_argument("--from-json", default="", help="solo reescribe el markdown desde un JSON")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = Path(a.out)
    if a.from_json:
        res = json.loads(Path(a.from_json).read_text(encoding="utf-8"))
        out.with_suffix(".md").write_text(er.render(res), encoding="utf-8")
        print(f"informe reescrito desde {a.from_json}")
        return 0
    data = Path(a.data)
    if data.resolve() == Path("data").resolve():
        print("no se corre sobre el almacen vivo")
        return 2
    pr, crit, t131 = load_prereg(), load_criteria(), load_t131()
    sym, t0 = pr.symbol, time.perf_counter()
    tmp = Path(tempfile.mkdtemp(prefix="t137_"))
    shutil.copy2(data / "paper.duckdb", tmp / "paper.duckdb")
    store, ps = Store(data), PaperStore(tmp / "paper.duckdb")
    desk = PaperDesk(store, ps, profiles=())
    ep, spec = desk.ep, spec_for(sym)
    ideas, path = load_world(store, ps, desk, sym)
    asof = int(path.end)
    log(t0, f"{len(ideas)} ideas, camino de {len(path.t)} velas, datos hasta {wf.iso(asof)}")

    # 1. registro y padres: la versión vigente de cada estrategia@marco
    vstore = ValidationStore(ps)
    registry = vstore.versions()
    parents = {v.sid: v for v in registry if v.retired_ms is None}
    for tf in ep.timeframes:
        for info in CATALOG.values():
            sid = f"{info.id}@{tf}"
            if info.runs_in(tf) and parents[sid].fingerprint != info.version(tf, ep):
                raise SystemExit(f"{sid}: la huella del código no es la del registro")
    prior = {f"{s}|{sid}@v{n}": p for (s, sid, n), p in vstore.last_pvalues(crit.version).items()}
    for v in registry:
        prior.setdefault(f"{sym}|{v.label}", None)
    log(t0, f"registro: {len(registry)} versiones, {len(prior)} claves previas")

    # 2. cuantil de M8 sin fuga: salida de referencia sobre las ideas que entraron en la sombra
    base_ideas = [o.idea for o in run_shadow(ideas, path, ep)]
    real = [i for i in base_ideas if i.strategy != pr.strategies.control]
    ctx = ExitContext(path=path, ep=ep, spec=spec)
    m1 = ShadowExit(id=pr.geometry.m8.reference, label=pr.geometry.m8.reference,
                    overrides={"be_trigger_r": 1.0, "be_lock_r": 0.1})
    ref = bench.run(real, [m1], ctx, t131.risk_usd).trades(m1.id, paired_only=False)
    atr = features.build(path, pr.geometry.s1.sigma)
    park = features.build(path, pr.geometry.m8.mae_sigma)
    plan = ev.fold_plan(pr)
    book = ev.quantile_book(ref, ev.mae_ratio(park, path.t, {i.id: i for i in real}), plan, pr)
    log(t0, f"cuantiles de M8: {len(ref)} operaciones de referencia; "
            f"{sum(len(w.by_sid) for bf in book.by_tf.values() for w in bf.per_fold)} con muestra")
    del ref, park
    gc.collect()

    # 3. una versión por variante y estrategia@marco, con su huella
    sids = sorted(parents)
    fps = {v.id: {s: ev.fingerprint(parents[s].fingerprint, v, pr, book.table(s)) for s in sids}
           for v in pr.variants}
    versions = [(ev.version_of(s, v, pr, fps[v.id][s], parents[s].n), v.id)
                for v in pr.variants for s in sids]
    variant_of = {x.label: vid for x, vid in versions}
    family = run.holm_family(prior, sym, [x for x, _ in versions])
    if len(family) != pr.attempts.family:
        raise SystemExit(f"familia de Holm: {len(family)} ≠ {pr.attempts.family} declaradas")

    # 4. cada variante corre su propia sombra
    start = iso_ms(pr.reading("banco").ranges[0][0])
    flip_from = FAR if a.sample_only else start
    runs = {ev.BASE: run.run_variant(ideas, ev.rule_of(None, pr, atr, path.t, None, spec.tick), {},
                                     path, ep, ev.FAR_MS, start)}
    for v in pr.variants:
        rule = ev.rule_of(v, pr, atr, path.t, book.of, spec.tick)
        runs[v.id] = run.run_variant(ideas, rule, fps[v.id], path, ep, flip_from, start)
        log(t0, f"variante {v.id}: {sum(len(x) for x in runs[v.id].trades.values())} cerradas")

    sample = run.sample_table(pr, crit, versions, runs, registry, parents, sym, asof)
    say_sample(sample)
    if a.sample_only:
        ps.close()
        shutil.rmtree(tmp, ignore_errors=True)
        return 0

    # 5. regresión contra lo publicado, y control con entradas al azar
    fine = PricePath.from_arrays(store.read_arrays(sym, "1m"), tf_ms("1m"))
    reg = None
    if not a.no_regression:
        tfs = {"1h", "4h"}
        reg = ec.regression(
            [i for i in real if i.timeframe in tfs],
            ExitContext(path=path, ep=ep, spec=spec, fine=fine), book, atr, pr,
            LADDER_BY_PROFILE["moderado"], t131.risk_usd, published(Path("reports")))
        log(t0, f"regresión: {[(k, x['ok']) for k, x in reg.items()]}")
    csid = f"{pr.control.strategy}@{pr.control.timeframe}"
    g = ec.control_geometry([i for i in ideas if i.sid == csid])
    q0 = book.of(csid, iso_ms(pr.m8_folds.after_bank.test_from))
    null, moved = ec.null_gross(pr, [ev.BASE, *(v.id for v in pr.variants)], fine.c,
                                float(path.c[0]), int(path.t[0]), g, ep, spec.tick, q0,
                                log=lambda m: log(t0, m))
    control = ec.control_report(pr, runs, null, moved, iso_ms(pr.control.real_from))
    del fine
    gc.collect()
    log(t0, "control listo")

    # 6. la puerta, tal cual, en las tres lecturas
    prices = (path.t, path.c)
    by_reading, res_read = {}, {}
    inert = {x.label: run.is_inert(runs[vid], x.sid, pr.variant(vid).geometry is not None)
             for x, vid in versions}
    for r in pr.readings:
        vs = run.score_reading(r, versions, runs, registry, family, crit, sym, asof, prices)
        by_reading[r.id] = vs
        rows = [er.row_of(r.id, x, variant_of[x.version.label],
                          runs[variant_of[x.version.label]].stats.get(x.version.sid),
                          inert[x.version.label]) for x in vs]
        res_read[r.id] = {
            "summary": summarize([x.to_json() for x in vs]), "rows": rows,
            "meets_v1": sum(1 for x in rows if x["V1"] is True),
            "pooled": sample[r.id]["pooled"], "period": r.note}
        log(t0, f"lectura {r.id}: {res_read[r.id]['summary']['counts']}")

    tf15 = run.tf15_block(pr, runs, [v.id for v in pr.variants], asof)
    res = {
        "meta": {"data": a.data, "symbol": sym, "commit": _head(), "prereg": pr.version,
                 "prereg_sha256": pr.sha256, "prereg_commit": PREREG_COMMIT,
                 "criteria": crit.version, "criteria_sha256": crit.sha256, "asof": wf.iso(asof),
                 "attempts": len(versions), "family": len(family), "null_reps":
                 crit.null_reps(len(family)), "ideas": len(ideas), "csv":
                 str(out.with_suffix(".csv")).replace("\\", "/"),
                 "seconds": round(time.perf_counter() - t0, 1),
                 "command": f"python scripts/t137_entrada.py --data {a.data}"},
        "variant_ids": [v.id for v in pr.variants],
        "readings": res_read,
        "variants": {k: {"cost": run.cost_summary(x),
                         "inert": sum(1 for lb, i in inert.items() if i and variant_of[lb] == k)}
                     for k, x in runs.items()},
        "cap_left_out": run.cap_left_out(sample["banco"]["pooled"], tf15["pooled"]),
        "control": control, "regression": reg, "tf15m": tf15,
        "m8_quantiles": {tf: bf.to_json() for tf, bf in book.by_tf.items()},
        "candidates": run.candidates(pr, by_reading, inert, variant_of, control),
    }
    write_outputs(out, res)
    write_attempts(ATTEMPTS_FILE, pr.version, pr.sha256, [x for x, _ in versions], variant_of)
    ps.close()
    shutil.rmtree(tmp, ignore_errors=True)
    log(t0, f"informe en {out.with_suffix('.md')}; candidatas: {len(res['candidates'])}")
    return 0


FAR = ev.FAR_MS


def _head() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          check=False).stdout.strip()


def write_outputs(out: Path, res: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [x for r in res["readings"].values() for x in r["rows"]]
    with out.with_suffix(".csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=er.CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    keep = {**res, "readings": {k: {**r, "rows": [
        {f: _round(x.get(f)) for f in er.CSV_FIELDS if f not in ("reason", "strategy")}
        for x in r["rows"] if x["n"] >= 100]} for k, r in res["readings"].items()}}
    out.with_suffix(".json").write_text(
        json.dumps(keep, ensure_ascii=False, indent=0, default=_num), encoding="utf-8")
    out.with_suffix(".md").write_text(er.render(res), encoding="utf-8")


def _round(x):
    return round(x, 5) if isinstance(x, float) else x


def _num(x):
    return x.item() if isinstance(x, np.generic) else str(x)


if __name__ == "__main__":
    raise SystemExit(main())
