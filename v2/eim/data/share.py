"""Experiencia compartida entre equipos (T61): exportar e importar historiales.

    python -m eim.data.share export             # al cerrar la jornada
    python -m eim.data.share import             # simulacro: qué traería de las demás máquinas
    python -m eim.data.share import --apply     # aplica (copia previa, una transacción por base)
    python -m eim.data.share status

Variables: `EIM_SHARED_DIR` (carpeta de nube compartida; cada máquina escribe SOLO en su
subcarpeta), `EIM_MACHINE` (alias de esta máquina), `EIM_DATA_DIR`, `EIM_BACKUP_DIR`.
Siempre SIMULADO; nunca se exportan claves ni el estado de la máquina (kill-switch, latidos).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from eim.data.local_api import DEFAULT_API
from eim.data.machine import machine_id
from eim.data.share_export import ShareError, export
from eim.data.share_import import discover, import_all
from eim.data.share_snap import HotSnapshots


def _shared(a: argparse.Namespace) -> Path:
    if not a.shared_dir:
        raise ShareError("define EIM_SHARED_DIR (carpeta de nube compartida) o usa --shared-dir")
    return Path(a.shared_dir)


def _status(a: argparse.Namespace, machine: str) -> int:
    shared = _shared(a)
    print(f"esta máquina: {machine} · datos: {a.data_dir} · compartida: {shared}")
    found, rejected = discover(shared, "", None)
    for e in found:
        mark = " (esta)" if e.machine == machine else ""
        print(f"  {e.machine}{mark}: última exportación {e.created_at} · "
              f"{sum(t['rows'] for t in e.manifest['tables'].values())} filas")
    for r in rejected:
        print(f"  RECHAZADA {r['machine']}: " + "; ".join(r["problems"]))
    return 0


def main(argv: list[str] | None = None) -> int:
    env = os.environ
    ap = argparse.ArgumentParser(prog="python -m eim.data.share")
    ap.add_argument("cmd", choices=["export", "import", "status"])
    ap.add_argument("--data-dir", type=Path, default=Path(env.get("EIM_DATA_DIR", "data")))
    ap.add_argument("--shared-dir", default=env.get("EIM_SHARED_DIR"))
    ap.add_argument("--backup-dir", type=Path, default=Path(env.get("EIM_BACKUP_DIR", "backups")))
    ap.add_argument("--api", default=DEFAULT_API, help="si la base está en uso, copia en caliente")
    ap.add_argument("--apply", action="store_true", help="import: aplicar (por defecto simulacro)")
    ap.add_argument("--from", dest="only", action="append", help="import: solo esa(s) máquina(s)")
    ap.add_argument("--no-recompute", action="store_true",
                    help="import --apply: no recalcular los veredictos")
    a = ap.parse_args(argv)
    try:
        machine = machine_id(a.data_dir)
        if a.cmd == "status":
            return _status(a, machine)
        shared = _shared(a)
        if a.cmd == "export":
            out = export(a.data_dir, shared, machine, snapshotter=HotSnapshots(a.data_dir, a.api))
            print(f"exportado ({machine}): {out}")
            return 0
        rep = import_all(a.data_dir, shared, machine, apply=a.apply, backup_dir=a.backup_dir,
                         only=set(a.only) if a.only else None)
        print(rep.render())
        if a.apply and rep.exports and not a.no_recompute:
            from eim.data.share_derived import recompute
            print("\n".join(recompute(a.data_dir)))
        return 2 if rep.rejected else 0
    except ShareError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
