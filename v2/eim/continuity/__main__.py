"""CLI de continuidad entre equipos (T125), desde `v2/`:

    python -m eim.continuity check [--offline] [--json]   # al llegar a un equipo
    python -m eim.continuity publish [--no-share]          # al irse (y cada día, tarea de Windows)
    python -m eim.continuity offsite list
    python -m eim.continuity offsite push [carpeta-de-copia]
    python -m eim.continuity offsite pull [--machine ID] [--backup eim_…]

Salida de `check`: 0 LISTO, 2 CON AVISOS, 1 NO SINCRONIZADO. `publish`: 0 todo bien, 2 algún
paso falló (queda en `data/continuity/publish.jsonl`). Variables: `EIM_DATA_DIR`,
`EIM_BACKUP_DIR`, `EIM_OFFSITE_REPO` (repo privado de datos), `EIM_OFFSITE_KEEP` (7).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from eim.continuity import check, offsite, publish
from eim.data.backup import listing
from eim.data.backup_restore import complete
from eim.data.local_api import DEFAULT_API
from eim.data.machine import machine_id

V2 = Path(__file__).resolve().parents[2]


def _offsite(a, t: offsite.Releases) -> int:
    if a.action == "list":
        copies = offsite.remote_copies(t)
        if a.json:
            print(json.dumps([{"machine": c.machine, "backup": c.backup,
                               "complete": c.complete, **c.meta} for c in copies],
                             ensure_ascii=False, indent=1))
            return 0
        if not copies:
            print(f"{t.repo}: sin copias externas")
        for c in copies:
            rows = sum(sum(v.values()) for v in c.rows.values())
            state = "completa" if c.complete else f"INCOMPLETA (faltan {len(c.missing)})"
            print(f"{c.machine}  {c.backup}  {state}  {c.meta.get('zip_bytes', 0) / 1e6:,.0f} MB"
                  f"  {rows:,} filas  desde {c.meta.get('host', '?')}  "
                  f"publicada {str(c.meta.get('published_at', '?'))[:16]}")
        return 0
    if a.action == "push":
        mine = machine_id(a.data_dir)
        target = Path(a.backup) if a.backup else next(
            (p for p in reversed(listing(a.backup_dir)) if complete(p)), None)
        if target is None:
            print("no hay copias locales completas: python -m eim.data.backup create")
            return 1
        meta = offsite.push(t, target, mine, work=a.backup_dir / publish.WORK)
        print(f"{'ya estaba' if meta['skipped'] else 'subida'}: {mine}{offsite.SEP}{target.name}"
              f" · {meta['zip_bytes'] / 1e6:,.0f} MB en {len(meta['parts'])} parte(s)")
        return 0
    copies = [c for c in offsite.remote_copies(t) if c.complete]
    if a.machine:
        copies = [c for c in copies if c.machine == a.machine]
    if a.backup:
        copies = [c for c in copies if c.backup == a.backup]
    if not copies:
        print("no hay ninguna copia externa completa que coincida (offsite list)")
        return 1
    pick = max(copies, key=lambda c: str(c.meta.get("published_at", "")))
    print(f"descargando {pick.machine}{offsite.SEP}{pick.backup} "
          f"({pick.meta.get('zip_bytes', 0) / 1e6:,.0f} MB)…", flush=True)
    out = offsite.pull(t, pick, a.backup_dir)
    print(f"verificada: {out}\nPara usarla (con la API y los líderes DETENIDOS; la base actual "
          f"se conserva con sufijo):\n  python -m eim.data.backup restore \"{out}\"")
    return 0


def main(argv: list[str] | None = None) -> int:
    env = os.environ
    if hasattr(sys.stdout, "reconfigure"):    # salida redirigida en Windows (cp1252)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m eim.continuity")
    ap.add_argument("--data-dir", type=Path, default=Path(env.get("EIM_DATA_DIR", "data")))
    ap.add_argument("--backup-dir", type=Path, default=Path(env.get("EIM_BACKUP_DIR", "backups")))
    ap.add_argument("--repo", default=offsite.repo_from_env(), help="repo privado de datos")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="¿este equipo está al día? (no modifica nada)")
    c.add_argument("--offline", action="store_true", help="sin red (no consulta la central)")
    c.add_argument("--json", action="store_true")
    p = sub.add_parser("publish", help="copia + copia externa + experiencia + aviso de código")
    p.add_argument("--no-share", action="store_true", help="sin exportar la experiencia")
    p.add_argument("--keep", type=int, default=int(env.get("EIM_OFFSITE_KEEP", "7")))
    p.add_argument("--max-age-h", type=float, default=26.0,
                   help="reutiliza la copia local si es más nueva que esto")
    p.add_argument("--api", default=DEFAULT_API)
    o = sub.add_parser("offsite", help="copias completas fuera del equipo")
    o.add_argument("action", choices=["list", "push", "pull"])
    o.add_argument("backup", nargs="?", help="push: carpeta; pull: usa --backup")
    o.add_argument("--machine", default=None, help="pull: de qué equipo")
    o.add_argument("--backup", dest="backup_name", default=None, help="pull: qué copia")
    o.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "check":
            r = check.run(V2, a.data_dir, a.backup_dir, network=not a.offline,
                          env={**env, "EIM_OFFSITE_REPO": a.repo})
            check.record(r, a.data_dir)
            print(json.dumps({"verdict": r.verdict[0], "findings": [vars(f) for f in r.findings],
                              "facts": r.facts}, ensure_ascii=False, indent=1, default=str)
                  if a.json else check.render(r))
            return r.verdict[1]
        if a.cmd == "publish":
            print(f"publicando el estado de este equipo en {a.repo}…", flush=True)
            res = publish.publish(V2, a.data_dir, a.backup_dir, repo=a.repo,
                                  machine=machine_id(a.data_dir), api=a.api,
                                  share=not a.no_share, keep=a.keep, max_age_h=a.max_age_h)
            print(f"{'PUBLICADO' if res['ok'] else 'PUBLICACIÓN INCOMPLETA'} en {res['seconds']} s"
                  " (registro: data/continuity/publish.jsonl)")
            return 0 if res["ok"] else 2
        if a.action == "pull":
            a.backup = a.backup_name
        return _offsite(a, offsite.Releases(a.repo))
    except offsite.OffsiteError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
