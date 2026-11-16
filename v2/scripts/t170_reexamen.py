"""T170: examen físico de las dos reglas rediseñadas antes del pre-registro (sin rendimiento).

`estructura_ruptura` y `tec_acuerdo_marcos` no se cumplían nunca en T169 (`PLAN/notas/
T169_examen_fisico.md`). El usuario eligió rediseñarlas antes de congelar `cantera_v1` (◆ T170,
2026-11-16). Este script las examina con **la misma ficha de T169** (`exam/verdict.judge`, banda
medida) y **los contextos que T169 ya guardó** (`backups/t169_examen/ctx_1h.jsonl`), sin regenerar
nada, porque las dos leen solo variables que ya están en ellos. No calcula R neto, acierto ni PF.

La no anticipación se hereda: T169 recalculó 162 contextos con el banco truncado y no encontró
ninguno distinto, y las ideas de una regla pura son función de esos contextos (≤ t).

    python scripts/t170_reexamen.py --work ../../../../v2/backups/t169_examen \
        --out reports/t170_reexamen
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # el `eim` de este checkout
sys.path.insert(0, str(Path(__file__).resolve().parent))      # t169_examen (mismas utilidades)

import numpy as np  # noqa: E402
import t169_examen as t169  # noqa: E402

from eim.nursery.exam import gen, plan, report, verdict  # noqa: E402
from eim.nursery.exam.physical import physics  # noqa: E402
from eim.nursery.prospect import load_prospects  # noqa: E402

REDESIGNED = ("estructura_ruptura", "tec_acuerdo_marcos")
FIELDS = ("ideas", "filled", "unfilled", "ops_month", "cost_r_mean", "hold_h_median",
          "pos_days_frac")


def _row(p, ph: dict, v: dict, old_fp: str | None) -> dict:
    return {"id": p.id, "agent": p.agent_id, "timeframe": p.timeframe, "role": p.role,
            "exit_template": p.exit_template, "declared_band": p.horizon,
            "fingerprint_t169": old_fp, "fingerprint_t170": p.fingerprint,
            "rule": p.rule_text, "params": p.params, "physics": ph, "verdict": v}


def _md(data: dict) -> str:
    lines = ["# T170 — Examen físico de las dos reglas rediseñadas", "",
             "**Modo: SIMULADO.** Sin rendimiento: ni R neto, ni acierto, ni PF. Misma ficha que "
             "T169 (`PLAN/T169.md`, banda medida) y mismos contextos guardados de 1 h "
             f"({data['contexts']} en {data['stretches']} tramos de 28 días, "
             f"{data['days']:.1f} días).".replace(f"{data['days']:.1f}",
                                                 f"{data['days']:.1f}".replace(".", ",")), "",
             "| Prospecto | Banda | Ideas | Operaciones | No llenadas | Al mes | Costo medio (R) "
             "| Tenencia mediana (h) | En posición (días) | Estado |",
             "|---|---|--:|--:|--:|--:|--:|--:|--:|---|"]
    for r in data["prospects"]:
        ph, v = r["physics"], r["verdict"]
        band = v["band"] if v["band"] == r["declared_band"] else \
            f"{v['band']} (declarada {r['declared_band']})"
        state = "**descartado**" if v["discarded"] else \
            ("sin opción a primer equipo" if v["no_first_team"] else "sigue")
        cost = "—" if ph.get("cost_r_mean") is None else f"{ph['cost_r_mean']:.3f}"
        hold = "—" if ph.get("hold_h_median") is None else f"{ph['hold_h_median']:.1f}"
        lines.append(f"| `{r['id']}` | {band} | {ph['ideas']} | {ph['filled']} | "
                     f"{ph['unfilled']} | {ph['ops_month']:.1f} | {cost} | {hold} | "
                     f"{round(ph['pos_days_frac'] * 100)}% | {state} |".replace(".", ","))
    lines += ["", "## Motivos y huellas", ""]
    for r in data["prospects"]:
        v = r["verdict"]
        why = "; ".join(v["reasons"]) or "cumple la ficha"
        edge = f" Al borde: {', '.join(v['borderline'])}." if v["borderline"] else ""
        lines.append(f"- `{r['id']}`: {why}.{edge} Huella T169 `{r['fingerprint_t169']}` → "
                     f"T170 `{r['fingerprint_t170']}`. Regla: {r['rule']}")
    lines += ["", "## No anticipación", "", data["lookahead_note"], ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--work", required=True, help="carpeta de trabajo de T169 (solo lectura)")
    ap.add_argument("--out", default="reports/t170_reexamen")
    a = ap.parse_args()
    work = Path(a.work)
    # No `t169._load_plan`: exige las huellas de T169, y justo estas dos cambiaron (rediseño).
    pl = json.loads((work / "plan.json").read_text(encoding="utf-8"))
    if plan.bank_files(Path(pl["bank"])) != pl["bank_files"]:
        raise SystemExit("el banco cambió desde T169: no es el mismo examen")
    look = json.loads((work / "lookahead.json").read_text(encoding="utf-8"))
    ctx_bad = sum(len(r.get("ctx_diff", [])) for r in look if r.get("tf") == "1h")
    n_look = sum(r.get("contexts", 0) for r in look if r.get("tf") == "1h")
    if ctx_bad:
        raise SystemExit("T169 halló contextos de 1 h distintos al truncar: no se hereda")
    prospects = {p.id: p for p in load_prospects() if p.id in REDESIGNED}
    path = t169._path(Path(pl["bank"]))
    ss = plan.stretches_of(pl)["1h"]
    allc = gen.load_ctxs(gen.ctx_path(work, "1h"))
    ts = np.array([int(c["t"]) for c in allc], dtype=np.int64)
    by = [(s, allc[int(np.searchsorted(ts, s.start, "right")):
                   int(np.searchsorted(ts, s.end, "right"))]) for s in ss]
    rows = []
    for pid in REDESIGNED:
        p = prospects[pid]
        ph = physics(p, by, path)
        v = verdict.judge(p.horizon, ph, False)
        rows.append(_row(p, ph, v, pl["prospects"].get(pid)))
        t169._say(f"{pid}: {ph['ideas']} ideas, {ph['filled']} operaciones, "
                  f"{'descartado' if v['discarded'] else 'sigue'}")
    data = {"task": "T170", "mode": "SIMULADO", "generated_utc": time.strftime(
        "%Y-%m-%dT%H:%MZ", time.gmtime()), "contexts": len(allc), "stretches": len(ss),
        "days": sum(s.days for s in ss), "prospects": rows,
        "lookahead_note": (f"Heredada de T169: {n_look} contextos de 1 h recalculados con el banco "
                           f"truncado, {ctx_bad} distintos. Las dos reglas son funciones puras de "
                           "esos contextos, así que sus ideas no pueden cambiar al truncar.")}
    md = _md(data)
    report.check_no_performance(data, md)
    out = Path(a.out)
    out.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    out.with_suffix(".md").write_text(md, encoding="utf-8")
    t169._say(f"informe en {out.with_suffix('.md')}")


if __name__ == "__main__":
    main()
