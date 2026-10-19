"""Experiencia compartida entre equipos (T61): exportar e importar historiales.

    python -m eim.data.share export             # al cerrar la jornada
    python -m eim.data.share import             # simulacro: qué traería de las demás máquinas
    python -m eim.data.share import --apply     # aplica (copia previa, una transacción por base)
    python -m eim.data.share status
    python -m eim.data.share setup --git-url <repo privado> [--machine alias]
    python -m eim.data.share setup --shared-dir <carpeta de nube> [--machine alias]

AUTOMÁTICO: tras `setup` (una vez) no hace falta ejecutar nada más: la API y el servicio de
líderes importan lo de las demás máquinas y exportan lo propio solos (`share_auto.py`). Los
comandos `export`/`import` quedan para uso manual, la primera importación de un equipo nuevo o
cuando no hay servicios en marcha.

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
from eim.data.share_auto import load_config, save_config
from eim.data.share_export import ShareError, export
from eim.data.share_git import GitError, GitTransport
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


def _setup(a: argparse.Namespace) -> int:
    if not (a.shared_dir or a.git_url):
        raise ShareError("indica --git-url <repo privado> o --shared-dir <carpeta de nube>")
    if a.shared_dir:
        Path(a.shared_dir).mkdir(parents=True, exist_ok=True)
    cfg = save_config(a.data_dir, a.shared_dir, a.machine, a.git_url)
    machine = machine_id(a.data_dir, {"EIM_MACHINE": a.machine or ""})
    where = f"repo privado {a.git_url}" if a.git_url else f"carpeta compartida {a.shared_dir}"
    print(f"configurado: máquina {machine} · {where}")
    print(f"guardado en {cfg}. Reinicia la API y el servicio de líderes: desde entonces "
          "importan y exportan solos (ver GET /v2/share/status).")
    return 0


def main(argv: list[str] | None = None) -> int:
    env = os.environ
    ap = argparse.ArgumentParser(prog="python -m eim.data.share")
    ap.add_argument("cmd", choices=["export", "import", "status", "setup"])
    ap.add_argument("--data-dir", type=Path, default=Path(env.get("EIM_DATA_DIR", "data")))
    ap.add_argument("--shared-dir", default=None)
    ap.add_argument("--backup-dir", type=Path, default=Path(env.get("EIM_BACKUP_DIR", "backups")))
    ap.add_argument("--api", default=DEFAULT_API, help="si la base está en uso, copia en caliente")
    ap.add_argument("--machine", default=None, help="setup: alias único de esta máquina")
    ap.add_argument("--git-url", default=None, help="setup: repo git PRIVADO que hace de nube")
    ap.add_argument("--apply", action="store_true", help="import: aplicar (por defecto simulacro)")
    ap.add_argument("--from", dest="only", action="append", help="import: solo esa(s) máquina(s)")
    ap.add_argument("--no-recompute", action="store_true",
                    help="import --apply: no recalcular los veredictos")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "setup":
            return _setup(a)
        cfg = load_config(a.data_dir)
        if not a.shared_dir:
            a.shared_dir = cfg.get("shared_dir")
        machine = machine_id(a.data_dir, {"EIM_MACHINE": os.environ.get("EIM_MACHINE")
                                          or cfg.get("machine", "")})
        git = None
        if cfg.get("git_url"):                  # transporte por repo privado (share_git.py)
            git = GitTransport(cfg["git_url"], a.data_dir / "share_repo", machine)
            a.shared_dir = str(git.view)
            if a.cmd != "export":
                print(f"git: traídas las exportaciones de {git.pull() or 'nadie (al día)'}")
            else:
                git.pull()
        if a.cmd == "status":
            return _status(a, machine)
        shared = _shared(a)
        if a.cmd == "export":
            out = export(a.data_dir, shared, machine, snapshotter=HotSnapshots(a.data_dir, a.api))
            print(f"exportado ({machine}): {out}")
            if git is not None:
                print("git: publicado" if git.push() else "git: sin cambios que publicar")
            return 0
        rep = import_all(a.data_dir, shared, machine, apply=a.apply, backup_dir=a.backup_dir,
                         only=set(a.only) if a.only else None)
        print(rep.render())
        if a.apply and rep.exports and not a.no_recompute:
            from eim.data.share_derived import recompute
            print("\n".join(recompute(a.data_dir)))
        return 2 if rep.rejected else 0
    except (ShareError, GitError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
