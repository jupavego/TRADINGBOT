"""T134 — el experimento pre-registrado de salidas, de una sola orden.

    python scripts/t134_exits_ab.py --data backups/t131_banco

Corre la rejilla del pre-registro `prereg_t131_v3` sobre la copia reconstruida de T131 y escribe
`reports/exits_ab.{json,md,csv}`. No elige nada: aplica los ocho criterios de §5.4 tal cual y la
decisión queda para el usuario (◆ de T134).

La aceptación pide que las cifras se reproduzcan **con una orden desde una copia**: esta es la
orden, y el informe guarda la huella del pre-registro, el commit y la semilla con los que salió.
No toca nada fuera de la copia y no abre red.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.paper.desk import PaperDesk
from eim.paper.engine import Path as PricePath
from eim.paper.exits import bench, experiment, features, grid, surrogate, winners_mae
from eim.paper.exits import walkforward as wf
from eim.paper.exits.costs import stressed
from eim.paper.exits.exits_report import render
from eim.paper.exits.policy import ExitContext
from eim.paper.exits.prereg import load_prereg
from eim.paper.exits.verdict import REJECTED
from eim.paper.ideas import Idea
from eim.paper.params import LADDER_BY_PROFILE, spec_for

SIGMAS = ("atr14", "parkinson", "garman_klass", "yang_zhang", "harrv_1m")
HTF_OF = {"15m": "1h", "1h": "4h", "4h": "4h"}
CONTROL_BARS = 4000          # velas de 15 m de cada serie sustituta
CONTROL_IDEAS = 300          # entradas al azar por sustituta


def _fine(store: Store, sym: str, tf: str) -> PricePath | None:
    if store.bounds(sym, tf) is None:
        return None
    return PricePath.from_arrays(store.read_arrays(sym, tf), tf_ms(tf))


def control_ideas_on(path: PricePath, seed: int, n: int, risk_frac: float = 0.01,
                     rr: float = 2.0) -> list[Idea]:
    """Entradas al azar sobre una serie sustituta, con la misma geometría relativa."""
    rng = np.random.default_rng([seed, 931])
    last = len(path.t) - 2
    if last < 2:
        return []
    picks = sorted(rng.choice(np.arange(1, last), size=min(n, last - 1), replace=False))
    out = []
    for k, j in enumerate(picks):
        side = 1 if rng.random() < 0.5 else -1
        px = float(path.c[j])
        d = px * risk_frac
        out.append(Idea(id=f"S{seed}:{k}", strategy=bench.CONTROL_STRATEGY, family="control",
                        symbol="BTCUSDT", t=int(path.t[j]) + path.step, side=side, kind="market",
                        entry=px, sl=px - side * d, tp=px + side * rr * d, fill_ms=0,
                        hold_ms=int(48 * 3_600_000), conf=0.5, why=("control",), timeframe="1h"))
    return out


def main() -> int:  # noqa: PLR0915
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="reports/exits_ab")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=experiment.BATCH)
    ap.add_argument("--no-control", action="store_true")
    ap.add_argument("--no-stress", action="store_true")
    ap.add_argument("--from-json", default="",
                    help="solo vuelve a escribir el informe desde un JSON ya calculado")
    a = ap.parse_args()
    data = Path(a.data)
    if data.resolve() == Path("data").resolve():
        print("no se corre sobre el almacen vivo")
        return 2
    if a.from_json:
        res = json.loads(Path(a.from_json).read_text(encoding="utf-8"))
        out = Path(a.out)
        out.with_suffix(".md").write_text(render(res), encoding="utf-8")
        print(f"informe reescrito desde {a.from_json}")
        return 0
    pr = load_prereg()
    sym = pr.symbol
    t0 = time.perf_counter()

    store, ps = Store(data), PaperStore(data / "paper.duckdb")
    desk = PaperDesk(store, ps, profiles=())
    v = desk.view(sym)
    if not v.outcomes or v.path is None:
        print("la copia no tiene contextos guardados")
        return 1
    fine = _fine(store, sym, pr.design.fine_timeframe)
    htf = _fine(store, sym, HTF_OF.get(pr.design.path_timeframe, "1h"))
    feats = {n: features.build(v.path, n, swing_bars=5, fine=fine, htf=htf) for n in SIGMAS}
    print(f"rasgos de {len(feats)} estimadores ({experiment.elapsed(t0)} s)", flush=True)

    tfs = set(pr.design.decision_timeframes)
    ideas = sorted((o.idea for o in v.outcomes
                    if o.idea.strategy != bench.CONTROL_STRATEGY and o.idea.timeframe in tfs),
                   key=lambda x: (x.t, x.id))
    if a.limit:
        ideas = ideas[:a.limit]
    ladder = LADDER_BY_PROFILE["moderado"]
    spec = spec_for(sym)
    ctx = ExitContext(path=v.path, ep=desk.ep, spec=spec, fine=fine)

    # 1-2. bases, pliegues y el cuantil del MAE de las ganadoras (E5).
    bases = _pick_bases(pr, feats, ladder, v.path.t)
    print(f"bases: {', '.join(x.id for x in bases)}", flush=True)
    b0 = bench.run(ideas, [x.policy for x in bases], ctx, pr.risk_usd)
    embargo = wf.embargo_for(
        [t for x in bases for t in b0.trades(x.id)],
        feature_ms=int(pr.design.embargo_feature_hours * 3_600_000),
        q=pr.design.embargo_quantile)
    lo, hi = wf.from_iso(pr.design.start), wf.from_iso(pr.design.end)
    if b0.rows:
        lo, hi = max(lo, b0.rows[0].t), min(hi, b0.rows[-1].t)
    fs = wf.folds(lo, hi, embargo, pr.design.fit_months, pr.design.test_months,
                  pr.design.step_months)
    ref_id = pr.winners_mae.reference if pr.winners_mae else bases[-1].id
    ref = next((x for x in bases if x.id.startswith(ref_id.split()[0])), bases[-1])
    ratio_of = _ratio_of(feats[SIGMAS[1]], v.path.t, {i.id: i for i in ideas})
    ref_trades = b0.trades(ref.id, paired_only=False)
    qs = sorted({float(q) for g in pr.grid if g.id == "M8" for q in g.params.get("q", ())})
    wmae_by_q = {q: winners_mae.build(ref_trades, fs, ratio_of, reference=ref.id,
                                      quantile=q, min_trades=pr.winners_mae.min_trades)
                 for q in qs} if pr.winners_mae else {}
    wmae = wmae_by_q.get(pr.winners_mae.quantile) if pr.winners_mae else None
    print(f"bases listas: {len(b0.paired())} emparejadas, {len(fs)} pliegues, embargo "
          f"{embargo / 3_600_000:.0f} h ({experiment.elapsed(t0)} s)", flush=True)
    del b0

    def quantile_for(q: float):
        w = wmae_by_q.get(q)
        return None if w is None else w.quantile_of()

    vs, skipped = grid.expand(pr, feats, ladder, v.path.t,
                              quantile_for=quantile_for if wmae_by_q else None,
                              est_cost_frac=desk.ep.est_cost_frac)
    print(f"rejilla: {len(vs)} variantes corribles, {len(skipped)} familias fuera", flush=True)

    tot = _run_all(ideas, bases, vs, ctx, pr, fs, a.batch, t0)
    mult = {x.id: experiment.multiplicity(pr, tot, x.id, "base") for x in bases}
    pbo = experiment.pbo_of(pr, tot)
    plateau = experiment.plateau_of(tot, vs, bases[0].id, pr.selection.plateau_keep)

    # 6. estrés de costos solo en las que pasan el criterio 1 (no cambia ningún veredicto).
    survivors = _survivors(pr, vs, bases, tot, mult)
    stress_tot, stress_mult = {}, {}
    if survivors and not a.no_stress:
        sctx = ExitContext(path=v.path, ep=stressed(desk.ep, pr.cost_stress.approve_at),
                           spec=spec, fine=fine)
        stress_tot = _run_all(ideas, bases, survivors, sctx, pr, fs, a.batch, t0)
        stress_mult = {x.id: experiment.multiplicity(pr, stress_tot, x.id, "stress")
                       for x in bases}
        print(f"estrés ×{pr.cost_stress.approve_at:g} en {len(survivors)} variantes "
              f"({experiment.elapsed(t0)} s)", flush=True)

    # 7. control aleatorio contra el nulo por sustitutas.
    control = {}
    if survivors and not a.no_control and fine is not None:
        null = experiment.control_null(
            pr, [*bases, *survivors], fine.c, float(v.path.c[0]), int(v.path.t[0]),
            CONTROL_BARS, desk.ep, spec,
            lambda p, s: control_ideas_on(p, s, CONTROL_IDEAS),
            log=lambda m: print(m, flush=True))
        real = _real_control(v, pr, [*bases, *survivors], ctx)
        control = {k: surrogate.verdict(real.get(k, float("nan")), null.get(k, []),
                                        pr.control.alpha) for k in null}
        print(f"control contra {pr.control.surrogates} sustitutas "
              f"({experiment.elapsed(t0)} s)", flush=True)

    verds = experiment.verdicts(pr, vs, bases, tot, mult, pbo, plateau, control,
                                stress_mult or None, stress_tot or None)
    res = _assemble(a, pr, v, fine, htf, feats, ideas, bases, vs, skipped, fs, embargo, tot,
                    mult, pbo, plateau, control, stress_tot, verds, wmae, t0)
    _write(Path(a.out), res, tot, verds)
    _say(res, verds)
    return 0


def _pick_bases(pr, feats, ladder, path_t):
    """Las dos bases: la escalera y la sombra con sus valores vigentes."""
    allv, _ = grid.expand(pr, feats, ladder, path_t, quantile_for=None)
    m0 = next(x for x in allv if x.family == "M0" and x.knobs.get("first_r") == 0.1)
    m1 = next(x for x in allv if x.family == "M1"
              and x.knobs.get("be_trigger_r") == 1.0 and x.knobs.get("be_lock_r") == 0.1)
    return [m0, m1]


def _ratio_of(f, path_t, by_id):
    """riesgo en precio / σ de cada operación, para pasar el MAE de R a σ (E5)."""
    def of(t):
        i = by_id.get(t.id)
        if i is None or not i.entry:
            return None
        j = int(np.searchsorted(path_t, i.t)) - 1
        if j < 0 or j >= len(f.sigma_abs):
            return None
        s = float(f.sigma_abs[j])
        risk = abs(i.entry - i.sl)
        return None if not np.isfinite(s) or s <= 0 or risk <= 0 else risk / s
    return of


def _run_all(ideas, bases, vs, ctx, pr, fs, batch, t0):
    """La rejilla por lotes, con las bases en cada uno para que el emparejado sea exacto."""
    cands = [x for x in vs if x.id not in {b.id for b in bases}]
    out: dict[str, experiment.Totals] = {}
    rng = np.random.default_rng(pr.seed)
    for k in range(0, len(cands), batch):
        chunk = cands[k:k + batch]
        got = experiment.run_batch(ideas, bases, chunk, ctx, pr, fs, rng)
        for key, val in got.items():
            out.setdefault(key, val)
        print(f"  lote {k // batch + 1}/{-(-len(cands) // batch)}: "
              f"{', '.join(x.id for x in chunk[:2])}… ({experiment.elapsed(t0)} s)", flush=True)
    return out


def _survivors(pr, vs, bases, tot, mult):
    """Las variantes que pasan el criterio 1 con el costo base."""
    base_ids = {b.id for b in bases}
    out = []
    for x in vs:
        if x.id in base_ids or x.id not in tot:
            continue
        good = True
        for b in base_ids:
            blk = mult.get(b, {})
            ci = blk.get("ci", {}).get(x.id)
            p = blk.get("p_rw", {}).get(x.id)
            good = good and ci is not None and ci[0] == ci[0] and ci[0] > 0 and (
                p is not None and p < pr.multiple.alpha)
        if good:
            out.append(x)
    return out


def _real_control(view, pr, variants, ctx):
    """El bruto del control aleatorio sobre la serie REAL (las ideas de `control_aleatorio`)."""
    ctrl = bench.control_ideas([o.idea for o in view.outcomes])
    if not ctrl:
        return {}
    b = bench.run(ctrl, [x.policy for x in variants], ctx, pr.risk_usd)
    out = {}
    for x in variants:
        ts = b.trades(x.id, paired_only=False)
        if ts:
            out[x.id] = float(np.mean([t.r + t.cost_r for t in ts]))
    return out


def _assemble(a, pr, view, fine, htf, feats, ideas, bases, vs, skipped, fs, embargo, tot, mult,
              pbo, plateau, control, stress_tot, verds, wmae, t0):
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True, check=False).stdout.strip()
    return {
        "meta": {"data": a.data, "symbol": pr.symbol, "commit": head,
                 "built": wf.iso(int(time.time() * 1000)), "prereg": pr.version,
                 "prereg_sha256": pr.sha256, "seed": pr.seed, "attempts": pr.attempts(),
                 "command": f"python scripts/t134_exits_ab.py --data {a.data}",
                 "fine_bars": 0 if fine is None else len(fine.t),
                 "htf_bars": 0 if htf is None else len(htf.t),
                 "ideas": len(ideas), "out": a.out, "seconds": experiment.elapsed(t0)},
        "window": {"from": wf.iso(fs[0].fit_from) if fs else None,
                   "to": wf.iso(fs[-1].test_to) if fs else None, "folds": len(fs),
                   "embargo_hours": round(embargo / 3_600_000, 2),
                   "folds_detail": [f.to_json() for f in fs]},
        "bases": [x.id for x in bases], "variants_run": len(tot),
        "grid_skipped": skipped,
        "feature_coverage": {n: f.to_json() for n, f in feats.items()},
        "winners_mae": wmae.to_json() if wmae else None,
        "metrics": {k: {"test": x.test, "all": x.all, "years": x.years, "folds": x.folds,
                        "cuts": x.cuts} for k, x in tot.items()},
        "multiplicity": mult, "pbo": pbo, "plateau": plateau, "control": control,
        "stress": {k: x.test for k, x in (stress_tot or {}).items()},
        "power_inputs": experiment.power_inputs(pr, tot, ideas, bases),
        "verdicts": [x.to_json() for x in verds],
        "libro_completo": ("solo es calculable para M0 y M1, las dos salidas que `paper/book.py` "
                           "sabe ejecutar; para las demás exige conectarlas a los perfiles, que "
                           "es T135 y está fuera del alcance de T134"),
    }


CUTS_KEPT = 10          # variantes (además de las bases) que conservan sus cortes en el JSON


def _trim(res: dict) -> dict:
    """El JSON sin los cortes de las variantes que nadie consideraría.

    Los cortes por régimen, marco, familia y lado de las 89 variantes son 6,8 MB de los 8,8 del
    archivo, y el informe más grande del repo son 610 KB. Se conservan los de las bases y las
    `CUTS_KEPT` mejores por E[R] —las únicas que alguien mirará— y el resto se regenera con la
    misma orden, que es justo lo que pide la aceptación de T134.
    """
    order = sorted(res["metrics"], key=lambda k: -(res["metrics"][k]["test"]
                                                   .get("expectancy_r") or -9e9))
    keep = set(res["bases"]) | set(order[:CUTS_KEPT])
    out = {**res, "metrics": {}}
    for k, v in res["metrics"].items():
        out["metrics"][k] = v if k in keep else {**v, "cuts": None}
    out["cuts_kept"] = sorted(keep)
    out["cuts_note"] = (f"Los cortes por régimen, marco, familia y lado se guardan de las bases y "
                        f"de las {CUTS_KEPT} mejores por E[R]; los de las demás se regeneran con "
                        f"`{res['meta']['command']}`.")
    return out


def _write(out: Path, res: dict, tot: dict, verds: list) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(_trim(res), ensure_ascii=False, indent=1,
                                                   default=str), encoding="utf-8")
    out.with_suffix(".md").write_text(render(res), encoding="utf-8")
    rows = []
    for k, x in tot.items():
        m = x.test
        rows.append({"variante": k, "n": m.get("n"), "expectancy_r": m.get("expectancy_r"),
                     "win_rate": m.get("win_rate"), "pf": m.get("pf"),
                     "cost_r": m.get("cost_r"), "max_dd_r": m.get("max_dd_r"),
                     "cvar95_r": m.get("cvar95_r"), "giveback_r": m.get("giveback_r"),
                     "veredicto": next((y.status for y in verds if y.variant == k), "base")})
    with out.with_suffix(".csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["variante"])
        w.writeheader()
        w.writerows(rows)


def _say(res: dict, verds: list) -> None:
    """Resumen por consola. Se fuerza UTF-8: la consola de Windows es cp1252 y una flecha o un
    guion largo la rompían DESPUÉS de haber escrito el informe, que es la peor forma de fallar."""
    from collections import Counter

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"\nveredictos: {dict(Counter(x.status for x in verds))}")
    for x in verds:
        if x.status != REJECTED:
            print(f"  {x.status}: {x.variant} - {x.reason}")
    print(f"\ninforme escrito en {res['meta']['out']} ({res['meta']['seconds']:.0f} s)")


if __name__ == "__main__":
    raise SystemExit(main())
