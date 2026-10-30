"""Publicar el estado de este equipo (T125): lo que hay que hacer al terminar una jornada o
antes de cambiar de equipo, y lo que corre solo cada día (`scripts/instalar_copia_externa.ps1`).

1. Copia completa de T115: la de hoy si ya existe (la hace el servicio a las 00:00 UTC) o una
   nueva (en caliente, pedida a la API si está en marcha).
2. `verify` de esa copia: una copia dañada no sale del equipo.
3. Extras (cambios sin confirmar, memoria de Claude, estado pequeño) y copia externa.
4. Poda de las copias externas propias (`EIM_OFFSITE_KEEP`, 7).
5. Experiencia compartida (T61/T117): exportación hecha DESDE LA COPIA, en una carpeta de
   trabajo propia. No toca la carpeta viva ni activa el modo automático; solo publica la rama
   `machine/<id>` de este equipo, sin importar nada de nadie.
6. Aviso del código que todavía no está en GitHub (eso lo sube el usuario: commit + push/PR).

Cada pasada deja una línea en `data/continuity/publish.jsonl`. Repetirla no duplica nada: la
copia externa ya subida se salta y la exportación de la misma copia ya existe.
"""

from __future__ import annotations

import json
import platform
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.continuity import datastate, extras, gitstate, offsite
from eim.data import backup as backup_cli
from eim.data.backup import listing
from eim.data.backup_restore import complete, verify
from eim.data.share_export import ShareError, export, prune_own
from eim.data.share_git import GitError, GitTransport

WORK = ".continuity"


def _fresh_copy(backup_dir: Path, max_age_h: float, now_s: float) -> Path | None:
    copies = [p for p in listing(backup_dir) if complete(p)]
    if not copies:
        return None
    t = datastate.stamp_s(copies[-1].name)
    return copies[-1] if t is not None and (now_s - t) / 3600.0 <= max_age_h else None


def share_from_copy(backup: Path, backup_dir: Path, url: str, machine: str) -> str:
    """Exporta la experiencia leyendo las bases DE LA COPIA (solo lectura: la copia sigue
    íntegra) y publica la rama `machine/<id>` con un clon propio en `backups/.continuity/`."""
    git = GitTransport(url, backup_dir / WORK / "share_repo", machine)
    git.prepare_own()
    stamp = datetime.strptime(backup.name[4:19], "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    try:
        out = export(backup, git.view, machine, now=stamp)
    except ShareError as e:
        if "ya existe" not in str(e):
            raise
        out = None
    prune_own(git.view, machine, "", 1)
    pushed = git.push()
    what = f"exportación {out.name}" if out else "exportación de esta copia ya hecha"
    return f"{what}; rama machine/{machine} " + ("publicada" if pushed else "sin cambios")


def publish(v2: Path, data_dir: Path, backup_dir: Path, *, repo: str, machine: str,
            api: str, share: bool = True, keep: int = 7, max_age_h: float = 26.0,
            transport: offsite.Releases | None = None, share_url: str | None = None,
            home: Path | None = None) -> dict:
    t0 = time.time()
    steps: list[dict] = []
    res = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "host": platform.node(),
           "machine": machine, "steps": steps}

    def step(name: str, ok: bool, text: str) -> bool:
        steps.append({"step": name, "ok": ok, "text": text})
        print(f"  {'OK   ' if ok else 'FALLO'} {name}: {text}", flush=True)
        return ok

    backup = _fresh_copy(backup_dir, max_age_h, t0)
    if backup is None:
        code = backup_cli.main(["create", "--data-dir", str(data_dir), "--dest", str(backup_dir),
                                "--api", api])
        backup = _fresh_copy(backup_dir, max_age_h, time.time())
        if backup is None:
            step("copia local", False, f"no se pudo hacer una copia completa (salida {code})")
            return _finish(res, data_dir, t0)
        step("copia local", True, f"{backup.name} (nueva)")
    else:
        step("copia local", True, f"{backup.name} (la de hoy)")
    if problems := verify(backup):
        step("verificación", False, "; ".join(problems))
        return _finish(res, data_dir, t0)
    step("verificación", True, "íntegra (SHA-256 y filas por tabla)")

    t = transport or offsite.Releases(repo)
    tmp = backup_dir / WORK / f"extras-{backup.name}"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        notes = extras.collect(tmp, v2, data_dir, home)
        ds = datastate.state(data_dir, backup_dir)
        info = {"host": platform.node(), "running": ds.running(),
                "code_head": gitstate.git(v2, "rev-parse", "HEAD", check=False).strip()}
        meta = offsite.push(t, backup, machine, extras=tmp, info=info, work=backup_dir / WORK)
        step("copia externa", True, f"{repo} · {meta['backup']} · "
             f"{meta['zip_bytes'] / 1e6:,.0f} MB en {len(meta['parts'])} parte(s)"
             + (" (ya estaba)" if meta["skipped"] else "") + " · " + "; ".join(notes))
        gone = offsite.prune(t, machine, keep)
        step("poda externa", True, f"{len(gone)} archivo(s) antiguos borrados (se conservan "
             f"las {keep} últimas de {machine})")
    except (offsite.OffsiteError, gitstate.GitFailed, OSError) as e:
        step("copia externa", False, str(e)[:400])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if share and (data_dir / "share_config.json").exists():
        step("experiencia", True, "modo automático de T61 activo en esta carpeta: exportan la API "
             "y el servicio de líderes (no se publica desde aquí para no pisar su rama)")
    elif share:
        try:
            step("experiencia", True, share_from_copy(
                backup, backup_dir, share_url or f"https://github.com/{repo}.git", machine))
        except (ShareError, GitError, OSError) as e:
            step("experiencia", False, str(e)[:400])

    try:
        c = gitstate.state(v2, fetch=False)
        pending = c.unpublished
        if c.ahead_upstream:
            pending.append(f"{c.branch}: {c.ahead_upstream} commit(s) sin push")
        step("código", True, "todo en GitHub" if not pending else
             "PENDIENTE de subir: " + "; ".join(pending) + " (va como parche en la copia externa)")
    except gitstate.GitFailed as e:
        step("código", False, str(e)[:200])
    return _finish(res, data_dir, t0)


def _finish(res: dict, data_dir: Path, t0: float) -> dict:
    res["seconds"] = round(time.time() - t0, 1)
    res["ok"] = all(s["ok"] for s in res["steps"])
    d = Path(data_dir) / "continuity"
    d.mkdir(parents=True, exist_ok=True)
    with (d / "publish.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(res, ensure_ascii=False) + "\n")
    return res
