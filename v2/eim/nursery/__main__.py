"""Consola de la cantera (fase 27). Hoy: `report`, el informe mensual de ojeo (T172). SIMULADO.

    python -m eim.nursery report                 # informe con lo que haya, ahora
    python -m eim.nursery report --si-toca       # solo si pasó una revisión sin informe (tarea)
    python -m eim.nursery report --db backups/eim_…/paper_cantera.duckdb

Solo lee el libro; escribe el informe en `reports/nursery/`, el resumen `latest.json` y, tras una
revisión, los hechos de aprendizaje en `data/library/digital/nursery_facts.jsonl`. No toca la
cantera, la síntesis, el consenso ni los libros de T31.
Salida: 0 = informe escrito o no tocaba; 2 = no se pudo leer el libro.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


def _report(a: argparse.Namespace) -> int:
    from eim.nursery.prereg import load_prereg
    from eim.nursery.report import run, source

    pr = load_prereg(a.prereg)
    asof = (int(datetime.fromisoformat(a.asof.replace("Z", "+00:00")).timestamp() * 1000)
            if a.asof else None)
    try:
        snap = source.load(pr, a.data_dir, a.backups, a.db, asof,
                           with_regimes=False if a.sin_regimenes else None)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2
    if a.si_toca and not run.due(a.out, snap.alta_ms, pr.ladder, snap.asof_ms):
        print("La cantera no tiene revisión nueva: no toca informe.")
        return 0
    r = run.build(snap, run.literature_of())
    s = run.write(r, a.out, a.data_dir, record_facts=not a.sin_biblioteca, backlog=a.backlog)
    print(f"Informe de la cantera {r['date']} (día {r['elapsed_days']:.1f}, revisiones "
          f"{r['reviews_done']}): {s['paths']['md']}")
    print(f"Etapas: {r['stages']}; hechos nuevos en la biblioteca: {r['library']['added']}; "
          f"bajas {len(r['improvement']['drops'])}; propuestas ◆ "
          f"{len(r['improvement']['proposals'])}.")
    for w in r["snapshot"]["warnings"]:
        print(f"Aviso: {w}")
    return 0


def main(argv: list[str] | None = None) -> int:
    env = os.environ
    ap = argparse.ArgumentParser(prog="python -m eim.nursery", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("report", help="informe mensual de ojeo y retroalimentación (T172)")
    rp.add_argument("--prereg", default="prereg_cantera_v1")
    rp.add_argument("--data-dir", type=Path, default=Path(env.get("EIM_DATA_DIR", "data")))
    rp.add_argument("--backups", type=Path, default=Path(env.get("EIM_BACKUP_DIR", "backups")))
    rp.add_argument("--db", type=Path, help="base de la cantera a leer (p. ej. de una copia)")
    rp.add_argument("--out", type=Path, default=Path("reports/nursery"))
    rp.add_argument("--asof", help="lectura hasta esta hora ISO (UTC); por defecto, ahora")
    rp.add_argument("--si-toca", action="store_true",
                    help="solo si pasó una revisión que el último informe no recoge")
    rp.add_argument("--sin-biblioteca", action="store_true",
                    help="no anotar los hechos de aprendizaje en la biblioteca")
    rp.add_argument("--sin-regimenes", action="store_true",
                    help="no leer los regímenes de paper.duckdb (solo los usa la mirada final)")
    rp.add_argument("--backlog", type=Path,
                    help="añadir a este BACKLOG las mejoras de agente que falten")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return _report(a)


if __name__ == "__main__":
    raise SystemExit(main())
