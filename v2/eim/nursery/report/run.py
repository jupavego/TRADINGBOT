"""Arma, escribe y reparte el informe mensual de la cantera (T172).

`build` es puro: del `Snapshot` al informe completo (dict). `write` deja el Markdown y el JSON en
`reports/nursery/cantera_<fecha>.{md,json}`, el resumen `latest.json` para la auditoría (T159) y,
**solo cuando ya hubo alguna revisión**, los hechos de aprendizaje en la biblioteca (registro de
solo adición, idempotente por clave). Con `--backlog` añade a `PLAN/BACKLOG.md` las líneas de
mejora de agentes que aún no estén.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from eim.nursery.ladder import BAJA, GUARDERIA, Standing, review_times
from eim.nursery.prospect import load_dossiers
from eim.nursery.report import feedback, measures, render
from eim.nursery.report.rows import Snapshot, account_data, standings

MARK = "<!-- T172 cantera -->"


def literature_of(dossiers: Mapping[str, dict] | None = None) -> dict[str, list[dict]]:
    """Obras que cita cada prospecto, con el concepto y la postura que les da su expediente."""
    out: dict[str, list[dict]] = {}
    for d in (dossiers if dossiers is not None else load_dossiers()).values():
        works: dict[str, list[dict]] = {}
        for w in d.get("literature") or ():
            works.setdefault(w["id"], []).append(w)
        for p in d.get("prospects") or ():
            rows = []
            for wid in p.get("literature") or ():
                meta = works.get(wid) or [{}]
                rows.append({"work": wid, "concept": meta[0].get("concept"),
                             "stance": meta[0].get("stance")})
            out[p["id"]] = rows
    return out


def _moves(stand: Mapping[str, Standing], last: int | None) -> list[dict]:
    if last is None:
        return []
    out = []
    for pid, s in stand.items():
        if s.since_ms != last or s.stage == GUARDERIA:
            continue
        if s.stage == BAJA:
            why = (s.exit or {}).get("motivo", "")
        else:
            why = "; ".join(c["motivo"] for c in s.criteria if c.get("ok")) or "cumple su etapa"
        out.append({"id": pid, "stage": s.stage, "motivo": why})
    return sorted(out, key=lambda m: (m["stage"], m["id"]))


def build(snap: Snapshot, literature: Mapping[str, Sequence[dict]]) -> dict:
    """El informe completo (puro)."""
    pr = snap.prereg
    data = account_data(snap)
    stand = standings(snap, data)
    rows = measures.prospect_rows(snap, stand)
    times = review_times(snap.alta_ms, pr.ladder)
    done = [t for t in times if t <= snap.asof_ms]
    facts = feedback.library_facts(snap, stand, literature, len(done),
                                   done[-1] if done else None) if done else []
    imp = feedback.improvement(snap, stand, rows)
    by_v: dict[str, int] = {}
    for f in facts:
        by_v[f["verdict"]] = by_v.get(f["verdict"], 0) + 1
    asof = datetime.fromtimestamp(snap.asof_ms / 1000, UTC)
    return {
        "mode": "SIMULADO", "task": "T172", "date": asof.strftime("%Y-%m-%d"),
        "snapshot": {"prereg": pr.version, "sha256": pr.sha256, "source": snap.source,
                     "alta_ms": snap.alta_ms, "asof_ms": snap.asof_ms,
                     "warnings": list(snap.warnings)},
        "elapsed_days": measures.elapsed_days(snap), "deadline_days": pr.ladder.deadline_days,
        "reviews_ms": times, "reviews_done": len(done),
        "next_review_ms": next((t for t in times if t > snap.asof_ms), None),
        "false_promises": {k: pr.false_promises.get(k) for k in ("mean", "p_at_least_one",
                                                                 "p95", "max", "bound")},
        "buy_hold": snap.buy_hold, "prospects": rows,
        "stages": {k: sum(1 for r in rows if r["stage"] == k) for k in sorted(
            {r["stage"] for r in rows})},
        "moves": _moves(stand, done[-1] if done else None),
        "theories": measures.theories(snap, data),
        "native_vs_generic": measures.native_vs_generic(snap, data),
        "family": measures.family_shape(snap, data), "early": measures.early_signals(rows),
        "events": measures.auto_adapt_events(snap),
        "library": {"review": len(done) or None, "facts": len(facts), "by_verdict": by_v,
                    "added": 0, "items": facts},
        "improvement": imp, "informativity": feedback.informativity(snap, rows),
        "graduations": feedback.graduations(snap, stand, data),
        "closure": feedback.closure(snap, stand),
    }


def latest(r: dict, paths: Mapping[str, str]) -> dict:
    """Resumen para la auditoría semanal (T159, nota §9.4): describe, no es una mirada."""
    imp = r["improvement"]
    opps = ([{"route": "auto", "text": f"{len(r['events'])} eventos de AUTO_ADAPT"}] +
            [{"route": "variante", "text": f"variante de ejecución en {v['timeframe']}"}
             for v in imp["variants"]] +
            [{"route": "◆", "text": f"versión nueva de {p['id']} ({p['cause']})"}
             for p in imp["proposals"] if p["fits"]] +
            [{"route": "◆", "text": f"graduación de {g['id']}"} for g in r["graduations"]] +
            [{"route": "esperar", "text": f"{sum(1 for p in r['prospects'] if p['n'] < 30)} "
                                          "prospectos con n < 30"}])
    return {"mode": "SIMULADO", "date": r["date"], "asof_ms": r["snapshot"]["asof_ms"],
            "prereg": r["snapshot"]["prereg"], "elapsed_days": r["elapsed_days"],
            "reviews_done": r["reviews_done"], "next_review_ms": r["next_review_ms"],
            "stages": r["stages"], "n_closed": sum(p["n"] for p in r["prospects"]),
            "best_net_return_pct": max((p["net_return_pct"] for p in r["prospects"]),
                                       default=None),
            "median_net_return_pct": _median([p["net_return_pct"] for p in r["prospects"]
                                              if p["n"]]),
            "buy_hold_pct": (r.get("buy_hold") or {}).get("return_pct"),
            "events": len(r["events"]), "library": {k: r["library"][k] for k in
                                                    ("review", "facts", "by_verdict", "added")},
            "informativity": r["informativity"]["agents"], "opportunities": opps,
            "warnings": r["snapshot"]["warnings"], "paths": dict(paths)}


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = len(s) // 2
    return s[k] if len(s) % 2 else round((s[k - 1] + s[k]) / 2, 3)


def append_backlog(path: Path, lines: Sequence[str], date: str) -> int:
    """Añade a BACKLOG las líneas de mejora que aún no estén (una por prospecto dado de baja)."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    new = []
    for ln in lines:
        m = re.search(r"el prospecto `([^`]+)`", ln)
        if m and f"el prospecto `{m.group(1)}`" not in text:
            new.append(ln)
    if new:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n{MARK} informe de la cantera del {date}\n" + "\n".join(new) + "\n")
    return len(new)


def write(r: dict, out: Path, data_dir: Path | None, record_facts: bool = True,
          backlog: Path | None = None) -> dict:
    """Escribe el informe, el resumen y (si hubo revisión) los hechos de la biblioteca."""
    out.mkdir(parents=True, exist_ok=True)
    if record_facts and data_dir is not None and r["library"]["items"]:
        from eim.data.library_digital import DigitalPaths, append_nursery_facts

        r["library"]["added"] = append_nursery_facts(
            DigitalPaths(data_dir / "library" / "digital"), r["library"]["items"])
    if backlog is not None and r["improvement"]["backlog"]:
        r["improvement"]["backlog_added"] = append_backlog(backlog, r["improvement"]["backlog"],
                                                           r["date"])
    base = out / f"cantera_{r['date']}"
    paths = {"md": str(base.with_suffix(".md")), "json": str(base.with_suffix(".json"))}
    base.with_suffix(".json").write_text(json.dumps(r, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    base.with_suffix(".md").write_text(render.markdown(r), encoding="utf-8")
    summary = latest(r, paths)
    (out / "latest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    return summary


def due(out: Path, alta_ms: int, rules, now_ms: int) -> bool:
    """¿Toca informe? Sí si ya pasó una revisión que el último informe no recoge."""
    done = sum(1 for t in review_times(alta_ms, rules) if t <= now_ms)
    try:
        prev = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return done > 0
    return done > int(prev.get("reviews_done") or 0)
