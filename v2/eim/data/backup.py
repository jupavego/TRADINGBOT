"""Copias de seguridad del almacén y de la configuración (T32).

Una copia es una carpeta `eim_AAAAMMDD-HHMMSS/` con:
- `reports.duckdb`: copia consistente de la base (reportes, decisiones de riesgo, libro simulado,
  alertas, capital, pronósticos). En caliente se hace dentro del proceso de la API, bajo el mismo
  cerrojo que usan los escritores (`COPY FROM DATABASE`); en frío, adjuntando la base en lectura.
- `state/`: kill-switch, estado del servicio de operación y registros JSONL.
- `config/`: versiones de parámetros (`eim/risk/versions`, `eim/calibration/versions`).
- `market/` (opcional, `--with-market`): velas/funding en parquet; se pueden volver a descargar.
- `manifest.json`: SHA-256 y tamaño de cada archivo, filas por tabla, commit de git.

Nunca se copian secretos: las claves viven solo en variables de entorno.

CLI (desde `v2/`): `python -m eim.data.backup create|verify|restore|list` (ver `main`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

import duckdb

PKG = Path(__file__).resolve().parents[1]                  # v2/eim
CONFIG_DIRS = {"risk": PKG / "risk" / "versions", "calibration": PKG / "calibration" / "versions"}
DB_NAME = "reports.duckdb"
PREFIX = "eim_"


class BackupError(RuntimeError):
    pass


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PKG, capture_output=True,
                             text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _tables(con) -> dict[str, int]:
    names = [r[0] for r in con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE database_name = current_database() "
        "ORDER BY table_name").fetchall()]
    return {n: con.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0] for n in names}


def copy_db_hot(con, lock, dst: Path) -> dict[str, int]:
    """Copia consistente desde la conexión abierta de la API (mismo cerrojo que los escritores)."""
    with lock or nullcontext():
        src = con.execute("SELECT current_database()").fetchone()[0]
        con.execute(f"ATTACH '{dst.as_posix()}' AS eim_backup")
        try:
            con.execute(f'COPY FROM DATABASE "{src}" TO eim_backup')
        finally:
            con.execute("DETACH eim_backup")
        return _tables(con)


def copy_db_cold(src: Path, dst: Path) -> dict[str, int]:
    """Copia con la API detenida. Si la base está en uso → BackupError (usar la vía API)."""
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{src.as_posix()}' AS src (READ_ONLY)")
    except (duckdb.IOException, duckdb.BinderException) as e:   # otro proceso / este mismo
        raise BackupError(f"la base está en uso (¿API en marcha?): {e}") from e
    try:
        con.execute(f"ATTACH '{dst.as_posix()}' AS eim_backup")
        con.execute("COPY FROM DATABASE src TO eim_backup")
        con.execute("USE src")
        return _tables(con)
    finally:
        con.close()


def _copy_tree(src: Path, dst: Path, pattern: str = "*") -> None:
    for p in sorted(src.rglob(pattern)) if src.exists() else []:
        if p.is_file() and not p.name.endswith(".tmp"):
            q = dst / p.relative_to(src)
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)


def create(data_dir: Path, dest_root: Path, *, con=None, lock: threading.Lock | None = None,
           with_market: bool = False, keep: int = 14,
           clock: Callable[[], float] = time.time) -> Path:
    """Crea una copia y poda las más antiguas (se conservan `keep`). Devuelve su carpeta."""
    stamp = datetime.fromtimestamp(clock(), UTC).strftime("%Y%m%d-%H%M%S")
    out = dest_root / f"{PREFIX}{stamp}"
    tmp = dest_root / f".{PREFIX}{stamp}.partial"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        db = tmp / DB_NAME
        if con is not None:
            tables = copy_db_hot(con, lock, db)
        elif (data_dir / DB_NAME).exists():
            tables = copy_db_cold(data_dir / DB_NAME, db)
        else:
            tables = {}
        if (data_dir / "kill_switch.json").exists():
            (tmp / "state").mkdir(exist_ok=True)
            shutil.copy2(data_dir / "kill_switch.json", tmp / "state" / "kill_switch.json")
        _copy_tree(data_dir / "operation", tmp / "state" / "operation")
        for name, d in CONFIG_DIRS.items():
            _copy_tree(d, tmp / "config" / name, "*.json")
        if with_market:
            for sub in ("candles", "funding"):
                _copy_tree(data_dir / sub, tmp / "market" / sub)
        files = {p.relative_to(tmp).as_posix(): {"sha256": _sha256(p), "bytes": p.stat().st_size}
                 for p in sorted(tmp.rglob("*")) if p.is_file()}
        manifest = {"created_at": stamp, "git_commit": _git_commit(), "data_dir": str(data_dir),
                    "with_market": with_market, "tables": tables, "files": files}
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        tmp.replace(out)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    prune(dest_root, keep)
    return out


def listing(dest_root: Path) -> list[Path]:
    return sorted(p for p in dest_root.glob(f"{PREFIX}*") if p.is_dir()) \
        if dest_root.exists() else []


def prune(dest_root: Path, keep: int) -> list[Path]:
    old = listing(dest_root)[:-keep] if keep > 0 else []
    for p in old:
        shutil.rmtree(p)
    return old


def verify(backup: Path) -> list[str]:
    """Problemas encontrados (vacío = copia íntegra): hashes, archivos y filas por tabla."""
    mf = backup / "manifest.json"
    if not mf.exists():
        return ["falta manifest.json"]
    m = json.loads(mf.read_text(encoding="utf-8"))
    problems = []
    for rel, meta in m["files"].items():
        p = backup / rel
        if not p.exists():
            problems.append(f"falta {rel}")
        elif _sha256(p) != meta["sha256"]:
            problems.append(f"hash distinto: {rel}")
    if (backup / DB_NAME).exists() and not problems:
        con = duckdb.connect(str(backup / DB_NAME), read_only=True)
        try:
            got = _tables(con)
        finally:
            con.close()
        if got != m["tables"]:
            problems.append(f"filas por tabla distintas: {got} ≠ {m['tables']}")
    return problems


def restore(backup: Path, data_dir: Path) -> list[str]:
    """Restaura base y estado en `data_dir` (API DETENIDA). La base actual se conserva como
    `reports.duckdb.antes-de-restaurar`. La configuración versionada vive en git: no se pisa."""
    problems = verify(backup)
    if problems:
        raise BackupError("copia no íntegra: " + "; ".join(problems))
    db = data_dir / DB_NAME
    data_dir.mkdir(parents=True, exist_ok=True)
    restored = []
    if (backup / DB_NAME).exists():
        if db.exists():
            try:          # otro proceso con la base abierta: bloqueo de DuckDB / de Windows
                duckdb.connect(str(db)).close()
                os.replace(db, db.with_name(DB_NAME + ".antes-de-restaurar"))
            except (duckdb.IOException, PermissionError) as e:
                raise BackupError(f"detén la API antes de restaurar: {e}") from e
        db.with_name(DB_NAME + ".wal").unlink(missing_ok=True)
        shutil.copy2(backup / DB_NAME, db)
        restored.append(DB_NAME)
    state = backup / "state"
    if (state / "kill_switch.json").exists():
        shutil.copy2(state / "kill_switch.json", data_dir / "kill_switch.json")
        restored.append("kill_switch.json")
    if (state / "operation").exists():
        _copy_tree(state / "operation", data_dir / "operation")
        restored.append("operation/")
    if (backup / "market").exists():
        _copy_tree(backup / "market", data_dir)
        restored.append("market")
    return restored


def due_today(dest_root: Path, now_s: float) -> bool:
    """¿Falta la copia del día UTC? (para la copia diaria automática del servicio)."""
    day = datetime.fromtimestamp(now_s, UTC).strftime("%Y%m%d")
    return not any(p.name.startswith(f"{PREFIX}{day}") for p in listing(dest_root))


def _via_api(api: str) -> dict:
    req = urllib.request.Request(f"{api}/v2/backup", method="POST",
                                 headers={"X-EIM-Confirm": "backup"})
    with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310 - API local del usuario
        return json.loads(resp.read())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eim.data.backup")
    ap.add_argument("cmd", choices=["create", "verify", "restore", "list"])
    ap.add_argument("backup", nargs="?", help="carpeta de la copia (verify/restore)")
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--dest", type=Path, default=Path("backups"))
    ap.add_argument("--keep", type=int, default=14)
    ap.add_argument("--with-market", action="store_true")
    ap.add_argument("--api", default="http://127.0.0.1:8000",
                    help="si la base está en uso, la copia la hace la API en marcha")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for p in listing(a.dest):
            print(p)
        return 0
    if a.cmd == "create":
        try:
            out = create(a.data_dir, a.dest, with_market=a.with_market, keep=a.keep)
        except BackupError as e:
            print(f"{e} → pidiendo la copia a la API ({a.api})")
            print(json.dumps(_via_api(a.api), ensure_ascii=False, indent=1))
            return 0
        print(out)
        return 0
    target = Path(a.backup) if a.backup else (listing(a.dest) or [None])[-1]
    if target is None:
        print("no hay copias")
        return 1
    if a.cmd == "verify":
        problems = verify(target)
        print(f"{target}: " + ("íntegra" if not problems else "; ".join(problems)))
        return 1 if problems else 0
    print("restaurado:", restore(target, a.data_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
