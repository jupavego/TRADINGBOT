"""Copias de seguridad de todo el historial y de la configuración (T32, T115).

Una copia es una carpeta `eim_AAAAMMDD-HHMMSS/` con:
- las bases (`eim/data/backup_dbs.py`): `reports.duckdb` (reportes, decisiones de riesgo, libro
  de planes, alertas, capital, pronósticos), `paper.duckdb` (bróker simulado: contextos,
  operaciones, validación y el registro inmutable de sugerencias de T51), `leaders.duckdb`
  (capturas en vivo de líderes, irrepetibles) y `obs.duckdb` (observatorio, derivado). Cada una
  por su camino: en caliente si la tiene abierta su dueño (API o servicio de líderes), en frío
  si nadie la usa; si está en uso y su dueño no responde, *ausente con motivo* en el manifiesto.
- `state/`: kill-switch, estado de la operación, registros JSONL y QC de la captura HFT (T78).
- `config/`: versiones de parámetros (`eim/risk/versions`, `eim/calibration/versions`).
- `market/` (opcional, `--with-market`): velas/funding en parquet; se pueden volver a descargar.
- `manifest.json`: SHA-256 y tamaño de cada archivo, filas por tabla de cada base, camino y
  segundos de cada copia, bases ausentes, commit de git.

Nunca se copian secretos: las claves viven solo en variables de entorno. Verificar y restaurar:
`eim/data/backup_restore.py`. CLI (desde `v2/`): `python -m eim.data.backup
create|verify|restore|list` (ver `main`).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
from collections.abc import Callable
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

from eim.data.backup_dbs import (
    API_DBS,
    DB_NAME,
    DBS,
    LEADERS,
    LEADERS_WAIT_S,
    OBS_NAME,
    PAPER,
    BackupError,
    DbBusy,
    copy_db,
    copy_db_cold,
    copy_db_hot,
    in_use,
    sha256,
)
from eim.data.backup_restore import complete, copy_tree, restore, summary, verify
from eim.data.local_api import DEFAULT_API, post_local

__all__ = ["DB_NAME", "LEADERS", "OBS_NAME", "PAPER", "BackupError", "DbBusy",
           "copy_db_cold", "copy_db_hot", "create", "due_today", "listing", "prune", "restore",
           "summary", "verify"]

PKG = Path(__file__).resolve().parents[1]                  # v2/eim
CONFIG_DIRS = {"risk": PKG / "risk" / "versions", "calibration": PKG / "calibration" / "versions"}
PREFIX = "eim_"
FORMAT = 2                                  # T115: `dbs` + `absent` (T32: `tables`/`extra_tables`)
PARTIAL_STALE_S = 3600.0                    # un `.partial` más viejo es de una copia interrumpida
API_TIMEOUT_S = LEADERS_WAIT_S + 300.0


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PKG, capture_output=True,
                             text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def create(data_dir: Path, dest_root: Path, *, con=None, lock: threading.Lock | None = None,
           hold=None, with_market: bool = False, keep: int = 14, extra_dbs: dict | None = None,
           strict: bool = True, leaders_wait_s: float | None = None,
           sleep: Callable[[float], None] = time.sleep,
           clock: Callable[[], float] = time.time) -> Path:
    """Crea una copia y poda las antiguas (`prune`). Devuelve su carpeta.

    `con`/`lock`: conexión abierta de `reports.duckdb`; `extra_dbs` = {nombre: (conexión,
    cerrojo)} de las demás bases que tiene abiertas este proceso (paper, observatorio). `hold`
    (el ciclo de operación) se retiene SOLO mientras se copian `reports.duckdb` y el estado del
    servicio, que deben ser coherentes entre sí; líderes, paper y observatorio se copian antes,
    sin él. `strict`: una base de la API en uso sin su conexión → BackupError al empezar (la CLI
    se la pide entonces a la API); si no, queda ausente con motivo."""
    t_start = time.perf_counter()
    wait = LEADERS_WAIT_S if leaders_wait_s is None else leaders_wait_s
    live = dict(extra_dbs or {})
    if con is not None:
        live[DB_NAME] = (con, lock)
    for name in API_DBS if strict else ():
        src = data_dir / DBS[name]
        if name not in live and src.exists() and (why := in_use(src)):
            raise DbBusy(f"{name} en uso (¿API en marcha?): {why}")
    stamp = datetime.fromtimestamp(clock(), UTC).strftime("%Y%m%d-%H%M%S")
    out, n = dest_root / f"{PREFIX}{stamp}", 1
    while out.exists():                          # dos copias en el mismo segundo
        n += 1
        out = dest_root / f"{PREFIX}{stamp}-{n}"
    tmp = dest_root / f".{out.name}.partial"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    dbs: dict[str, dict] = {}
    absent: dict[str, str] = {}

    def take(name: str) -> None:
        t0 = time.perf_counter()
        try:
            got = copy_db(name, data_dir, tmp / name, live.get(name), leaders_wait_s=wait,
                          sleep=sleep)
        except BackupError as e:
            if strict and name in API_DBS and isinstance(e, DbBusy):
                raise
            absent[name] = str(e)
            return
        if got is not None:
            dbs[name] = {"tables": got[0], "via": got[1],
                         "seconds": round(time.perf_counter() - t0, 2)}

    try:
        for name in (LEADERS, PAPER, OBS_NAME):  # sin `hold`: no dependen del ciclo
            take(name)
        with hold or nullcontext():
            t_hold = time.perf_counter()
            take(DB_NAME)
            if (data_dir / "kill_switch.json").exists():
                (tmp / "state").mkdir(exist_ok=True)
                shutil.copy2(data_dir / "kill_switch.json", tmp / "state" / "kill_switch.json")
            copy_tree(data_dir / "operation", tmp / "state" / "operation")
            held_s = round(time.perf_counter() - t_hold, 2)
        copy_tree(data_dir / "micro_hft" / "qc", tmp / "state" / "micro_hft_qc", "*.json")
        for name, d in CONFIG_DIRS.items():
            copy_tree(d, tmp / "config" / name, "*.json")
        if with_market:
            for sub in ("candles", "funding"):
                copy_tree(data_dir / sub, tmp / "market" / sub)
        files = {p.relative_to(tmp).as_posix(): {"sha256": sha256(p), "bytes": p.stat().st_size}
                 for p in sorted(tmp.rglob("*")) if p.is_file()}
        manifest = {"format": FORMAT, "created_at": stamp, "git_commit": _git_commit(),
                    "data_dir": str(data_dir), "with_market": with_market,
                    "dbs": {k: dbs[k] for k in DBS if k in dbs}, "absent": absent,
                    "held_s": held_s, "seconds": round(time.perf_counter() - t_start, 2),
                    "files": files}
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False),
                                           encoding="utf-8")
        tmp.replace(out)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    prune(dest_root, keep)
    return out


def listing(dest_root: Path) -> list[Path]:
    return sorted(p for p in dest_root.glob(f"{PREFIX}*") if p.is_dir()) \
        if dest_root.exists() else []


def _age_s(p: Path, now_s: float) -> float:
    return now_s - max((q.stat().st_mtime for q in (p, *p.rglob("*"))), default=now_s)


def prune(dest_root: Path, keep: int, now_s: float | None = None) -> list[Path]:
    """Conserva las `keep` copias COMPLETAS más recientes y, aparte, las `keep` más recientes de
    cualquier tipo: una copia con bases ausentes nunca empuja fuera a la última completa. Los
    restos `.partial` (copia interrumpida) nunca cuentan y se borran pasada `PARTIAL_STALE_S`
    (los más nuevos pueden ser una copia en curso de otro proceso)."""
    if keep <= 0:
        return []
    every = listing(dest_root)
    stay = set(every[-keep:]) | set([p for p in every if complete(p)][-keep:])
    old = [p for p in every if p not in stay]
    for p in old:
        shutil.rmtree(p)
    now = time.time() if now_s is None else now_s
    for p in sorted(dest_root.glob(f".{PREFIX}*.partial")) if dest_root.exists() else []:
        if _age_s(p, now) > PARTIAL_STALE_S:
            shutil.rmtree(p, ignore_errors=True)
            old.append(p)
    return old


def due_today(dest_root: Path, now_s: float) -> bool:
    """¿Falta la copia del día UTC? (para la copia diaria automática del servicio)."""
    day = datetime.fromtimestamp(now_s, UTC).strftime("%Y%m%d")
    return not any(p.name.startswith(f"{PREFIX}{day}") for p in listing(dest_root))


def _print_summary(s: dict, head: str) -> None:
    print(f"{s['path']}: {head}")
    for name, d in s["dbs"].items():
        t = d["tables"]
        how = f"{d['via']}, {d['seconds']} s" if d.get("via") else "copia de T32"
        print(f"  {name:<15} {len(t):>3} tablas {sum(t.values()):>13,} filas  ({how})")
    for name, why in s["absent"].items():
        print(f"  {name:<15} AUSENTE: {why}")
    if s.get("seconds") is not None:
        print(f"  {s['files']} archivos, {s['bytes'] / 1e6:.1f} MB, {s['seconds']} s "
              f"(ciclo de operación retenido {s['held_s']} s)")


def _create_cli(a) -> dict:
    """En frío; si una base de la API está en uso, se la pide a la API (que pide a su vez la de
    líderes a su servicio); sin API, en frío lo que esté libre y el resto ausente con motivo."""
    kw = {"with_market": a.with_market, "keep": a.keep}
    try:
        return summary(create(a.data_dir, a.dest, **kw))
    except BackupError as e:
        print(f"{e}\n→ pidiendo la copia a la API ({a.api})")
    q = "?with_market=true" if a.with_market else ""
    try:
        res = post_local(a.api, f"/v2/backup{q}", "backup", timeout=API_TIMEOUT_S)
    except (urllib.error.URLError, OSError) as e:
        print(f"la API no respondió ({e}): copia en frío; lo que siga en uso queda ausente")
    else:
        if "dbs" not in res:              # API en marcha con código anterior a T115
            res = {**res, "dbs": {}, "seconds": None, "absent": {
                "?": "la API en marcha es anterior a T115 (solo reports y observatorio): "
                     "reiníciala y repite"}}
        return res
    return summary(create(a.data_dir, a.dest, strict=False, **kw))


def main(argv: list[str] | None = None) -> int:
    """Mismos valores por defecto que la API (`EIM_DATA_DIR`, `EIM_BACKUP_DIR`,
    `EIM_BACKUP_KEEP`): la CLI encuentra las copias que hizo el servicio. Salida: 0 = copia
    íntegra y completa, 2 = íntegra con bases ausentes, 1 = dañada o sin copias."""
    env = os.environ
    ap = argparse.ArgumentParser(prog="eim.data.backup")
    ap.add_argument("cmd", choices=["create", "verify", "restore", "list"])
    ap.add_argument("backup", nargs="?", help="carpeta de la copia (verify/restore)")
    ap.add_argument("--data-dir", type=Path, default=Path(env.get("EIM_DATA_DIR", "data")))
    ap.add_argument("--dest", type=Path, default=Path(env.get("EIM_BACKUP_DIR", "backups")))
    ap.add_argument("--keep", type=int, default=int(env.get("EIM_BACKUP_KEEP", "14")))
    ap.add_argument("--with-market", action="store_true")
    ap.add_argument("--api", default=DEFAULT_API,
                    help="si una base está en uso, la copia la hace la API en marcha")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):   # salida redirigida en Windows (cp1252): «→», «≠»
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.cmd == "list":
        for p in listing(a.dest):
            print(f"{p}{'' if complete(p) else '  (incompleta)'}")
        return 0
    if a.cmd == "create":
        s = _create_cli(a)
        _print_summary(s, "copia hecha" if not s["absent"] else "copia INCOMPLETA")
        return 2 if s["absent"] else 0
    target = Path(a.backup) if a.backup else (listing(a.dest) or [None])[-1]
    if target is None:
        print("no hay copias")
        return 1
    if a.cmd == "verify":
        problems = verify(target)
        if problems:
            print(f"{target}: " + "; ".join(problems))
            return 1
        s = summary(target)
        _print_summary(s, "íntegra" if not s["absent"] else "íntegra pero INCOMPLETA")
        return 2 if s["absent"] else 0
    s = summary(target)
    print("restaurado:", restore(target, a.data_dir))
    for name, why in s["absent"].items():
        print(f"no estaba en la copia (se conserva la local): {name} — {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
