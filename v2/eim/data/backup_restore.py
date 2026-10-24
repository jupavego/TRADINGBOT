"""Leer, verificar y restaurar una copia de seguridad (T32, T115). Crear: `eim.data.backup`.

`verify` solo busca daños (archivo que falta, SHA-256 o filas por tabla distintas). Una base que
la copia declara *ausente con motivo* (`absent`: estaba en uso y su dueño no la entregó) no es un
daño: la copia es íntegra pero incompleta, y `restore` deja esa base local como está.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from eim.data.backup_dbs import DB_NAME, DBS, BackupError, count_file, in_use, sha256


def read_manifest(backup: Path) -> dict | None:
    try:
        return json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def manifest_dbs(m: dict) -> dict[str, dict]:
    """{base: {"tables", "via", "seconds"}} en el orden de `DBS`. Lee también el formato de T32
    (`tables` de reports + `extra_tables`), el de las copias anteriores a T115."""
    if "dbs" in m:
        got = m["dbs"]
    else:
        old = {DB_NAME: m.get("tables", {}), **m.get("extra_tables", {})}
        got = {n: {"tables": t, "via": None, "seconds": None} for n, t in old.items()
               if n in m.get("files", {})}
    return {n: got[n] for n in DBS if n in got}


def summary(backup: Path) -> dict:
    """Resumen para la CLI, la API y el registro del servicio."""
    m = read_manifest(backup) or {}
    files = m.get("files", {})
    return {"path": str(backup), "name": backup.name, "files": len(files),
            "bytes": sum(f["bytes"] for f in files.values()), "dbs": manifest_dbs(m),
            "absent": m.get("absent", {}), "seconds": m.get("seconds"),
            "held_s": m.get("held_s")}


def complete(backup: Path) -> bool:
    """¿Copia terminada y con todas sus bases? (las de T32 cuentan como completas)."""
    m = read_manifest(backup)
    return m is not None and not m.get("absent")


def verify(backup: Path) -> list[str]:
    """Problemas encontrados (vacío = copia íntegra): archivos, hashes y filas por tabla."""
    m = read_manifest(backup)
    if m is None:
        return ["falta manifest.json"]
    problems = []
    for rel, meta in m["files"].items():
        p = backup / rel
        if not p.exists():
            problems.append(f"falta {rel}")
        elif sha256(p) != meta["sha256"]:
            problems.append(f"hash distinto: {rel}")
    for name, d in manifest_dbs(m).items():
        if problems:
            break
        if not (backup / name).exists():
            problems.append(f"falta {name}")
        elif (got := count_file(backup / name)) != d["tables"]:
            problems.append(f"filas por tabla distintas en {name}: {got} ≠ {d['tables']}")
    return problems


def _set_aside(p: Path, suffix: str) -> None:
    """La base local (y su `.wal`, si quedó) pasa a `<nombre><sufijo>`: no se mezcla ni se borra."""
    for src, dst in ((p, p.with_name(p.name + suffix)),
                     (p.with_name(p.name + ".wal"), p.with_name(p.name + suffix + ".wal"))):
        if src.exists():
            os.replace(src, dst)


def copy_tree(src: Path, dst: Path, pattern: str = "*") -> None:
    for p in sorted(src.rglob(pattern)) if src.exists() else []:
        if p.is_file() and not p.name.endswith(".tmp"):
            q = dst / p.relative_to(src)
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)


def restore(backup: Path, data_dir: Path,
            clock: Callable[[], float] = time.time) -> list[str]:
    """Restaura en `data_dir` las bases de la copia, el kill-switch y el estado del servicio.

    Antes de tocar nada comprueba la copia (`verify`) y que ninguna base de destino esté abierta
    (API y servicio de líderes DETENIDOS): si algo falla, no cambia nada. Cada base se reemplaza
    entera; la anterior se conserva con el sufijo `.antes-de-restaurar-<AAAAMMDD-HHMMSS>` (cada
    restauración el suyo: restaurar dos veces no pierde el original). Una base ausente en la copia
    no se toca. La configuración versionada vive en git: no se pisa."""
    problems = verify(backup)
    if problems:
        raise BackupError("copia no íntegra: " + "; ".join(problems))
    targets = {n: data_dir / DBS[n] for n in manifest_dbs(read_manifest(backup))}
    busy = [n for n, p in targets.items() if p.exists() and in_use(p)]
    if busy:
        raise BackupError(f"detén la API y el servicio de líderes antes de restaurar (en uso: "
                          f"{', '.join(busy)}); no se ha tocado nada")
    suffix = ".antes-de-restaurar-" + datetime.fromtimestamp(clock(), UTC).strftime(
        "%Y%m%d-%H%M%S")
    restored = []
    for name, dst in targets.items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            _set_aside(dst, suffix)
        except PermissionError as e:          # bloqueo de Windows sin cerrojo de DuckDB
            raise BackupError(f"detén la API y el servicio de líderes antes de restaurar: {e} "
                              f"(ya restaurado: {restored or 'nada'})") from e
        shutil.copy2(backup / name, dst)
        restored.append(name)
    state = backup / "state"
    if (state / "kill_switch.json").exists():
        shutil.copy2(state / "kill_switch.json", data_dir / "kill_switch.json")
        restored.append("kill_switch.json")
    if (state / "operation").exists():
        op = data_dir / "operation"
        if op.exists():   # sin restos de un estado que la copia no tenía (p. ej. otro modo)
            op.rename(op.with_name("operation" + suffix))
        copy_tree(state / "operation", op)
        restored.append("operation/")
    if (backup / "market").exists():
        copy_tree(backup / "market", data_dir)
        restored.append("market")
    return restored
