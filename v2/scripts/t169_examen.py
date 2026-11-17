"""T169: examen físico de los prospectos de la cantera en la historia (sin rendimiento).

Por la cola de trabajos (`~/.claude/CLAUDE.md`), un proceso, sobre una COPIA del banco de T131:

    python scripts/t169_examen.py plan --bank backups/t169_examen/banco --work backups/t169_examen
    python scripts/t169_examen.py generate --work backups/t169_examen     # largo y reanudable
    python scripts/t169_examen.py identity --work backups/t169_examen
    python scripts/t169_examen.py lookahead --work backups/t169_examen
    python scripts/t169_examen.py exam --work backups/t169_examen --out reports/t169_examen_fisico

Desde un worktree, con `PYTHONPATH=.` o desde `v2/` (el script antepone el `eim` de su checkout).
Plan de muestreo y umbrales: `PLAN/T169.md`, fijados antes de correr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # el `eim` de este checkout

import duckdb  # noqa: E402
import numpy as np  # noqa: E402

from eim.data.store import Store  # noqa: E402
from eim.data.timeframes import tf_ms  # noqa: E402
from eim.nursery.exam import checks, gen, plan, report, verdict  # noqa: E402
from eim.nursery.exam.physical import physics  # noqa: E402
from eim.nursery.prospect import load_prospects  # noqa: E402
from eim.paper.engine import Path as PricePath  # noqa: E402

SYMBOL = "BTCUSDT"


def _rss_mb() -> float | None:
    try:
        from eim.operation import usage_win
        return round(usage_win.snapshot()[os.getpid()].ram / 2**20, 1)
    except (OSError, KeyError, ImportError, AttributeError):
        return None


def _say(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())} UTC] {msg}", flush=True)


def _load_plan(work: Path, verify: bool = True) -> dict:
    pl = json.loads((work / "plan.json").read_text(encoding="utf-8"))
    if verify and plan.bank_files(Path(pl["bank"])) != pl["bank_files"]:
        raise SystemExit("el banco cambió desde que se congeló la ventana: no se reanuda")
    now = {p.id: p.fingerprint for p in plan.with_history(load_prospects())}
    if now != pl["prospects"]:
        raise SystemExit("los prospectos cambiaron (huellas distintas): otra carpeta de trabajo")
    return pl


def cmd_plan(a: argparse.Namespace) -> None:
    bank = Path(a.bank).resolve()
    last = {}
    for tf in plan.TFS:
        f = bank / "candles" / f"symbol={SYMBOL}" / f"timeframe={tf}" / "data.parquet"
        mx = duckdb.connect().execute(f"SELECT max(t) FROM read_parquet('{f.as_posix()}')")
        last[tf] = int(mx.fetchone()[0]) + tf_ms(tf)
    pl = plan.freeze(Path(a.work) / "plan.json",
                     plan.build(load_prospects(), last, bank, plan.bank_files(bank)))
    for tf, ss in plan.stretches_of(pl).items():
        _say(f"{tf}: {len(ss)} tramos, {sum(len(s.asofs()) for s in ss)} contextos, "
             f"agentes {pl['agents'].get(tf)}")
    _say(f"prospectos con historia {len(pl['prospects'])}, sin historia "
         f"{len(pl['without_history'])}")


def cmd_generate(a: argparse.Namespace) -> None:
    work = Path(a.work)
    pl = _load_plan(work)
    store = Store(Path(pl["bank"]))
    native = {k: tuple(v) for k, v in pl["native"].items()}
    tfs = a.tf.split(",") if a.tf else list(plan.TFS)
    for tf in tfs:
        lg = gen.LightGen(store, tf, gen.agents_named(pl["agents"][tf]), native)
        asofs = [t for s in plan.stretches_of(pl)[tf] for t in s.asofs()]

        seen = {"s": 0.0, "rss": 0.0}

        def progress(k: int, n: int, dt: float, tf: str = tf, seen: dict = seen) -> None:
            seen["s"] = dt
            if k % a.every == 0 or k == n:
                rss = _rss_mb()
                seen["rss"] = max(seen["rss"], rss or 0.0)
                _say(f"{tf} {k}/{n} · {dt / k:.3f} s/contexto · faltan "
                     f"{(n - k) * dt / k / 3600:.2f} h · RAM {rss} MB")

        done = gen.run(lg, asofs, gen.ctx_path(work, tf), progress, a.limit)
        _say(f"{tf}: {done} contextos calculados en esta pasada")
        if done:
            with (work / "generate_log.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"tf": tf, "computed": done, "seconds": round(seen["s"], 1),
                                    "rss_mb_max": seen["rss"], "utc": time.strftime(
                                        "%Y-%m-%dT%H:%MZ", time.gmtime())}) + "\n")


def cmd_identity(a: argparse.Namespace) -> None:
    work = Path(a.work)
    rows = checks.subset_identity(_load_plan(work), work, load_prospects(), a.per_tf)
    (work / "identity.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    _say(f"identidad: {sum(r['identical'] for r in rows)}/{len(rows)} idénticos")


def cmd_lookahead(a: argparse.Namespace) -> None:
    work = Path(a.work)
    rows = checks.lookahead(_load_plan(work), work, load_prospects(), work / "_cortes")
    (work / "lookahead.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    bad = [r for r in rows if r.get("ctx_diff") or r.get("idea_diff") or r.get("missing")]
    _say(f"no anticipación: {len(rows)} cortes, {len(bad)} con diferencias")


def _path(bank: Path) -> PricePath:
    st = Store(bank)
    p = PricePath.from_arrays(st.read_arrays(SYMBOL, "15m"), tf_ms("15m"))
    fund = st.read_series("funding", SYMBOL)
    p.ft = np.array([t for t, _ in fund], dtype=np.int64)
    p.fr = np.array([x for _, x in fund], dtype=float)
    return p


def _checks_lines(work: Path) -> tuple[list[str], set[str], dict]:
    look = json.loads((work / "lookahead.json").read_text(encoding="utf-8"))
    ident = json.loads((work / "identity.json").read_text(encoding="utf-8"))
    flagged = {pid for r in look for pid in r.get("idea_diff", [])}
    n_ctx = sum(r.get("contexts", 0) for r in look)
    ctx_bad = sum(len(r.get("ctx_diff", [])) for r in look)
    lines = ["## Comprobaciones", "",
             f"- **No anticipación:** {len(look)} cortes (6 por marco), {n_ctx} contextos "
             f"recalculados con el banco truncado: {ctx_bad} distintos; prospectos cuyas ideas "
             f"cambian: {sorted(flagged) or 'ninguno'}.",
             f"- **Identidad del subconjunto:** {sum(r['identical'] for r in ident)} de "
             f"{len(ident)} contextos con `nat` idéntico al de la mesa con todos los agentes "
             "(los agentes sin historia no aportan nada en el banco)."]
    return lines, flagged, {"lookahead": look, "identity": ident}


def _cost(work: Path) -> dict:
    """Lo que costó generar, por marco, según el registro de cada pasada de `generate`."""
    out: dict[str, dict] = {}
    for r in gen.iter_rows(work / "generate_log.jsonl"):
        acc = out.setdefault(r["tf"], {"computed": 0, "seconds": 0.0, "rss_mb_max": 0.0,
                                       "passes": 0})
        acc["computed"] += r["computed"]
        acc["seconds"] = round(acc["seconds"] + r["seconds"], 1)
        acc["rss_mb_max"] = max(acc["rss_mb_max"], r.get("rss_mb_max") or 0.0)
        acc["passes"] += 1
    for acc in out.values():
        acc["s_per_ctx"] = round(acc["seconds"] / acc["computed"], 3) if acc["computed"] else None
    return out


def _dec(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def _ids(ids: list[str]) -> str:
    return ", ".join(f"`{i}`" for i in ids) or "ninguno"


def _twins(rows: list[dict]) -> list[list[str]]:
    """Prospectos con la misma física (sin contar la cobertura, que nombra otras variables)."""
    groups: dict[str, list[str]] = {}
    for r in rows:
        ph = {k: v for k, v in r["physics"].items() if k != "coverage"}
        if ph.get("ideas"):
            groups.setdefault(r["timeframe"] + json.dumps(ph, sort_keys=True), []).append(r["id"])
    return [g for g in groups.values() if len(g) > 1]


def _cost_line(cost: dict, contexts: int) -> str:
    if not cost:
        return "Costo de generación: sin registro de pasadas."
    tot = sum(c["seconds"] for c in cost.values())
    logged = sum(c["computed"] for c in cost.values())
    extra = (f" Los otros {contexts - logged} contextos salieron de pasadas de prueba anteriores "
             "al registro de costo." if contexts > logged else "")
    return ("Costo de generación (un proceso, en IDLE, por la cola): " + "; ".join(
        f"{tf} {c['computed']} contextos a {_dec(c['s_per_ctx'], 3)} s" for tf, c in cost.items())
        + f" → **{_dec(tot / 3600)} h de cálculo** ({_dec(tot / 86400, 2)} días de máquina) en "
        f"{sum(c['passes'] for c in cost.values())} pasadas; RAM máxima "
        f"{max(c['rss_mb_max'] for c in cost.values()):.0f} MB." + extra)


def cmd_exam(a: argparse.Namespace) -> None:
    work = Path(a.work)
    pl = _load_plan(work, verify=False)
    path = _path(Path(pl["bank"]))
    cost = _cost(work)
    lines_chk, flagged, chk = _checks_lines(work)
    rows, sample = [], {}
    by_tf_ctx = {}
    for tf, ss in plan.stretches_of(pl).items():
        if not pl["agents"].get(tf):
            continue                    # ningún prospecto en ese marco (T177: sin 15 m)
        allc = gen.load_ctxs(gen.ctx_path(work, tf))
        ts = np.array([int(c["t"]) for c in allc], dtype=np.int64)
        by_tf_ctx[tf] = [(s, allc[int(np.searchsorted(ts, s.start, "right")):
                                  int(np.searchsorted(ts, s.end, "right"))]) for s in ss]
        planned = {t for s in ss for t in s.asofs()}
        tried = {int(r["t"]) for r in gen.iter_rows(gen.ctx_path(work, tf))} & planned
        sample[tf] = {"stretches": len(ss), "contexts": len(allc), "expected": len(planned),
                      "skipped": len(tried) - len(allc), "days": round(sum(s.days for s in ss), 1)}
        if len(tried) < len(planned) and not a.allow_partial:
            raise SystemExit(f"{tf}: faltan {len(planned) - len(tried)} contextos del plan; "
                             "termina `generate` (o usa --allow-partial para una prueba)")
    for p in plan.with_history(load_prospects()):
        ph = physics(p, by_tf_ctx[p.timeframe], path)
        v = verdict.judge(p.horizon, ph, p.id in flagged)
        rows.append({"id": p.id, "agent": p.agent_id, "timeframe": p.timeframe,
                     "exit_template": p.exit_template, "role": p.role, "physics": ph,
                     "verdict": v})
        _say(f"{p.id}: {ph['filled']} operaciones, {'descartado' if v['discarded'] else 'sigue'}")
    disc = [r for r in rows if r["verdict"]["discarded"]]
    keep = [r for r in rows if not r["verdict"]["discarded"]]
    nofirst = [r for r in keep if r["verdict"]["no_first_team"]]
    by_band = [r["id"] for r in disc if r["verdict"]["kept_with_declared_band"]]
    dead = [r["id"] for r in rows if r["physics"]["ideas"] == 0]
    twins = _twins(rows)
    total = sum(s["contexts"] for s in sample.values())
    summary = [
        f"**{len(rows)} prospectos con historia examinados** de "
        f"{len(rows) + len(pl['without_history'])}: **{len(disc)} descartados** por razones "
        f"mecánicas y {len(keep)} siguen, de los que {len(nofirst)} quedan «sin opción a "
        "primer equipo» (no llegan a ≈ 100 operaciones, o a 120 días con posición, en 6 meses). "
        f"{sum(r['verdict']['reassigned'] for r in rows)} cambian de banda por su tenencia.",
        "", f"- **{len(by_band)} descartes dependen de la reasignación de banda**: con la banda "
        f"declarada seguirían ({_ids(by_band)}).",
        f"- **{len(dead)} reglas no se cumplen nunca** en la muestra ({_ids(dead)}): la causa "
        f"de cada una está en `{a.notes}`.",
        f"- **Gemelos físicos** (mismas ideas y operaciones): "
        f"{'; '.join(' = '.join(f'`{i}`' for i in g) for g in twins) or 'ninguno'}.",
        "", "Muestra: " + "; ".join(
            f"{tf} {s['contexts']} contextos de {s['expected']} en {s['stretches']} "
            f"tramo{'s' if s['stretches'] != 1 else ''} ({_dec(s['days'])} días)"
            for tf, s in sample.items()) + ".", "", _cost_line(cost, total)]
    data = {"task": a.task, "mode": "SIMULADO", "generated_utc": time.strftime(
        "%Y-%m-%dT%H:%MZ", time.gmtime()), "plan": pl, "sample": sample, "cost": cost,
        "thresholds": {"min_ops_month": verdict.MIN_OPS_MONTH,
                       "min_pos_days_frac": verdict.MIN_POS_DAYS_FRAC,
                       "max_cost_r": verdict.MAX_COST_R, "term_days": verdict.TERM_DAYS,
                       "first_team_ops": verdict.FIRST_TEAM_OPS,
                       "first_team_pos_days": verdict.FIRST_TEAM_POS_DAYS,
                       "sigma_r_assumed": verdict.SIGMA_R},
        "mintrl": verdict.mintrl_table(), "prospects": rows,
        "without_history": pl["without_history"], "checks": chk,
        "summary_lines": summary, "checks_lines": lines_chk}
    md = report.to_markdown(data)
    report.check_no_performance(data, md)
    out = Path(a.out)
    out.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    out.with_suffix(".md").write_text(md, encoding="utf-8")
    _say(f"informe en {out.with_suffix('.md')} y .json")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="T169: examen físico de la cantera")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("plan")
    s.add_argument("--bank", required=True)
    s.add_argument("--work", required=True)
    s = sub.add_parser("generate")
    s.add_argument("--work", required=True)
    s.add_argument("--tf", default="")
    s.add_argument("--limit", type=int, default=None)
    s.add_argument("--every", type=int, default=250)
    s = sub.add_parser("identity")
    s.add_argument("--work", required=True)
    s.add_argument("--per-tf", type=int, default=3)
    s = sub.add_parser("lookahead")
    s.add_argument("--work", required=True)
    s = sub.add_parser("exam")
    s.add_argument("--work", required=True)
    s.add_argument("--out", default="reports/t169_examen_fisico")
    s.add_argument("--task", default="T169")                  # T177 reutiliza el examen
    s.add_argument("--notes", default="PLAN/notas/T169_examen_fisico.md")
    s.add_argument("--allow-partial", action="store_true")
    a = ap.parse_args(argv)
    {"plan": cmd_plan, "generate": cmd_generate, "identity": cmd_identity,
     "lookahead": cmd_lookahead, "exam": cmd_exam}[a.cmd](a)


if __name__ == "__main__":
    main()
