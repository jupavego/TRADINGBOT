"""T131 — ¿la copia reconstruida es la MISMA historia que midió T111?

    python scripts/t131_t111_diff.py --new reports/t111_sobre_copia.json \
        --old reports/ppp_profiles_ab.json

Compara el A/B de T111 recalculado sobre la copia (`scripts/ppp_profiles_ab.py --data <copia>`)
con el informe guardado en el repo. El tramo **fuera de muestra** (ideas anteriores a
2026-08-16) tiene que salir idéntico: sus contextos son los mismos y sus operaciones cierran mucho
antes del final del camino. El tramo **dentro** no puede coincidir, porque desde T111 el almacén
siguió creciendo (más contextos y camino más largo): eso se informa, no se esconde.

Sin red y sin disco más allá de leer los dos JSON y escribir el resumen.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

KEYS = ("n", "wins", "losses", "win_rate", "net", "net_won", "net_lost", "pf", "expectancy_usd",
        "expectancy_r", "avg_win_r", "avg_loss_r", "max_dd_r")
TOL = 1e-9
PROFILES = ("conservador", "moderado", "agresivo")


def scenarios(seg: dict, pid: str) -> dict[str, dict]:
    """{etiqueta: métricas} de un perfil en un tramo (A y cada variante de B)."""
    blk = seg["profiles"][pid]
    out = {"A": blk["A"]["metrics"]}
    out.update({f"B/{k}": v["metrics"] for k, v in blk["B"].items()})
    return out


def compare(a: dict, b: dict) -> list[tuple[str, object, object]]:
    """Diferencias campo a campo de dos bloques de métricas."""
    bad = []
    for k in KEYS:
        x, y = a.get(k), b.get(k)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            if abs(float(x) - float(y)) > TOL * max(1.0, abs(float(x))):
                bad.append((k, x, y))
        elif x != y:
            bad.append((k, x, y))
    return bad


def diff_segment(old: dict, new: dict, name: str) -> dict:
    out: dict[str, dict] = {}
    for pid in PROFILES:
        so, sn = scenarios(old["segments"][name], pid), scenarios(new["segments"][name], pid)
        for lab in sorted(set(so) | set(sn)):
            if lab not in so or lab not in sn:
                out[f"{pid}|{lab}"] = {"missing_in": "viejo" if lab not in so else "nuevo"}
                continue
            bad = compare(so[lab], sn[lab])
            out[f"{pid}|{lab}"] = {"equal": not bad,
                                   "diffs": [{"field": k, "old": x, "new": y} for k, x, y in bad]}
    return out


def render(res: dict) -> str:
    out = ["# T131 — la copia reconstruida frente al informe de T111", "",
           f"Viejo: `{res['old']}` (commit `{res['old_commit']}`, {res['old_ideas']} ideas).",
           f"Nuevo: `{res['new']}` (commit `{res['new_commit']}`, {res['new_ideas']} ideas).", ""]
    for name, block in res["segments"].items():
        same = sum(1 for v in block.values() if v.get("equal"))
        out += [f"## Tramo «{name}»: {same} de {len(block)} escenarios idénticos", "",
                "| Escenario | ¿Idéntico? | Diferencias |", "|---|---|---|"]
        for lab, v in block.items():
            if v.get("missing_in"):
                out.append(f"| `{lab}` | — | falta en el informe {v['missing_in']} |")
                continue
            d = ("ninguna" if v["equal"] else
                 "; ".join(f"{x['field']}: {x['old']} → {x['new']}" for x in v["diffs"][:6]))
            out.append(f"| `{lab}` | {'sí' if v['equal'] else '**NO**'} | {d} |")
        out.append("")
    out += ["El tramo «fuera» es el que tiene que coincidir: mismos contextos y operaciones que "
            "cierran antes del final del camino de T111. El tramo «dentro» cambia por diseño: "
            "desde T111 el almacén ganó contextos y el camino llega más lejos.", ""]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--old", default="reports/ppp_profiles_ab.json")
    ap.add_argument("--new", required=True)
    ap.add_argument("--out", default="reports/t131_t111_diff")
    a = ap.parse_args()
    old = json.loads(Path(a.old).read_text(encoding="utf-8"))
    new = json.loads(Path(a.new).read_text(encoding="utf-8"))
    res = {"old": a.old, "new": a.new, "old_commit": old["meta"].get("commit"),
           "new_commit": new["meta"].get("commit"), "old_ideas": old["meta"].get("ideas"),
           "new_ideas": new["meta"].get("ideas"),
           "segments": {name: diff_segment(old, new, name)
                        for name in ("fuera", "dentro") if name in old["segments"]
                        and name in new["segments"]}}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    out.with_suffix(".md").write_text(render(res), encoding="utf-8")
    bad = sum(1 for v in res["segments"].get("fuera", {}).values() if not v.get("equal"))
    print(f"comparacion en {out.with_suffix('.md')}; escenarios distintos en «fuera»: {bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
