"""Exportación de la experiencia propia (T61): Parquet por tabla + `manifest.json`.

Destino: `<EIM_SHARED_DIR>/<máquina>/<AAAAMMDDTHHMMSSZ>/`. Un solo escritor por subcarpeta (la
nube no genera conflictos) y se escribe en `.<sello>.partial` y se renombra al final: quien lee
nunca ve una exportación a medias. Nunca se coloca una base DuckDB viva en la carpeta
sincronizada: se lee en frío (adjunta en solo lectura) o desde una copia coherente pedida al
proceso que la tiene abierta (`share_snap.HotSnapshots`).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import duckdb

from eim.data.backup_dbs import sha256 as _sha256
from eim.data.backup_dbs import sql_path as _sql_path
from eim.data.share_spec import DB_ORDER, FORMAT, PART_BYTES, SCHEMA_VERSION, specs_of

PKG = Path(__file__).resolve().parents[1]


class ShareError(RuntimeError):
    pass


class Snapshotter(Protocol):
    def __call__(self, db: str) -> Path: ...
    def close(self) -> None: ...


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PKG, capture_output=True,
                             text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def columns(con, alias: str, table: str) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in con.execute(
        "SELECT column_name, data_type FROM duckdb_columns() WHERE database_name = ? AND "
        "table_name = ? ORDER BY column_index", [alias, table]).fetchall()]


def _attach(path: Path):
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH {_sql_path(path)} AS src (READ_ONLY)")
    except (duckdb.IOException, duckdb.BinderException) as exc:
        con.close()
        raise ShareError(f"{path.name} está en uso: {exc}") from exc
    return con


def _split(con, f: Path, rows: int, part_bytes: int) -> list[dict]:
    """Trocea `f` (ya ordenado por la clave) por número de fila en partes de ~`part_bytes`:
    disjuntas, cubren todas las filas y conservan el orden. Borra `f` al terminar."""
    k = min(-(-f.stat().st_size // part_bytes), rows)
    per = -(-rows // k)
    parts = []
    for i in range(k):
        p = f.with_name(f"{f.stem}.part{i:03d}.parquet")
        con.execute(f"COPY (SELECT * EXCLUDE (file_row_number) FROM read_parquet("
                    f"{_sql_path(f)}, file_row_number = true) WHERE file_row_number >= {i * per} "
                    f"AND file_row_number < {(i + 1) * per}) TO {_sql_path(p)} "
                    "(FORMAT PARQUET, COMPRESSION ZSTD)")
        n = con.execute(f"SELECT count(*) FROM read_parquet({_sql_path(p)})").fetchone()[0]
        parts.append({"file": p.name, "rows": int(n), "sha256": _sha256(p)})
    f.unlink()
    return parts


def _write_db(con, db: str, out: Path, machine: str, tables: dict,
              part_bytes: int = PART_BYTES) -> None:
    for sp in specs_of(db):
        cols = columns(con, "src", sp.name)
        if not cols:
            continue
        names = [c for c, _ in cols]
        select = "*"
        if "machine" in sp.key and "machine" not in names:     # base previa a T61
            select, cols = f"*, '{machine}' AS machine", [*cols, ("machine", "VARCHAR")]
        order = ", ".join(f'"{k}"' for k in sp.key if k in {c for c, _ in cols}) or "1"
        f = out / f"{sp.name}.parquet"
        con.execute(f"COPY (SELECT {select} FROM src.main.\"{sp.name}\" ORDER BY {order}) "
                    f"TO {_sql_path(f)} (FORMAT PARQUET, COMPRESSION ZSTD)")
        rows = int(con.execute(f"SELECT count(*) FROM read_parquet({_sql_path(f)})"
                               ).fetchone()[0])
        meta = {"db": db, "rows": rows, "columns": [[c, t] for c, t in cols]}
        if f.stat().st_size > part_bytes and rows > 1:    # T117: git no admite > 90 MB
            meta["parts"] = _split(con, f, rows, part_bytes)
        else:
            meta |= {"file": f.name, "sha256": _sha256(f)}
        tables[sp.name] = meta


def prune_own(shared_dir: Path, machine: str, part: str, keep: int) -> list[Path]:
    """Borra las exportaciones propias más antiguas del mismo tipo (`part`), dejando `keep`
    (cada exportación es una foto completa: la nube no necesita acumularlas)."""
    root = shared_dir / machine
    dirs = [p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")
            ] if root.exists() else []
    mine = sorted(p for p in dirs
                  if (p.name.endswith(f"-{part}") if part else "-" not in p.name))
    old = mine[:-keep] if keep > 0 else []
    for p in old:
        shutil.rmtree(p, ignore_errors=True)
    return old


def export(data_dir: Path, shared_dir: Path, machine: str, *,
           snapshotter: Snapshotter | None = None, now: datetime | None = None,
           dbs: tuple[str, ...] = DB_ORDER, part: str = "", part_bytes: int = PART_BYTES
           ) -> Path:
    """Escribe la exportación y devuelve su carpeta. Una base ausente se anota y se sigue; una
    base en uso sin forma de copiarla en caliente es un error (no se exporta a medias).
    `dbs`/`part`: exportación parcial de un proceso que solo tiene algunas bases (la API:
    reports+paper; el servicio de líderes: leaders); el importador toma la más reciente de cada
    base. Una tabla de más de `part_bytes` viaja en varias partes (`parts` en el manifest)."""
    now = now or datetime.now(UTC)
    stamp = now.strftime("%Y%m%dT%H%M%SZ") + (f"-{part}" if part else "")
    root = shared_dir / machine
    final, tmp = root / stamp, root / f".{stamp}.partial"
    if final.exists():
        raise ShareError(f"ya existe una exportación de esta máquina en {stamp}")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    tables: dict = {}
    absent: dict[str, str] = {}
    try:
        for db in dbs:
            src = data_dir / db
            if not src.exists():
                absent[db] = "no existe en esta máquina"
                continue
            try:
                con = _attach(src)
            except ShareError:
                if snapshotter is None:
                    raise
                con = _attach(snapshotter(db))
            try:
                _write_db(con, db, tmp, machine, tables, part_bytes)
            finally:
                con.close()
        manifest = {"format": FORMAT, "schema_version": SCHEMA_VERSION, "machine": machine,
                    "created_at": stamp, "dbs": list(dbs), "git_commit": git_commit(),
                    "tables": tables, "absent": absent}
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        tmp.replace(final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    finally:
        if snapshotter is not None:
            snapshotter.close()
    return final
