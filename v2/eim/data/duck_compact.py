"""Compactado de una base DuckDB que nadie tiene abierta (T128, entregable 2).

DuckDB reutiliza los bloques libres, pero nunca encoge el archivo: el 2026-11-02
`leaders.duckdb` pesaba 2,1 GB con 1,34 GB en uso (su copia de la noche, que es compacta).
`compact` la copia a un archivo nuevo con la misma copia que la diaria (`COPY FROM DATABASE`,
que conserva claves y restricciones), comprueba las filas tabla a tabla y solo entonces cambia
un archivo por otro. Solo si lo libre pasa de `MIN_FREE` y el archivo de `MIN_BYTES`: copiar
1,3 GB tarda alrededor de un minuto. Lo llama el vigilante de líderes al arrancar, antes de
lanzar a su hijo `run`, el único que abre la base.

Si el cambio se corta a medias, la base vieja queda como `<nombre>.old` y la siguiente llamada
la devuelve a su sitio.
"""

from __future__ import annotations

import time
from pathlib import Path

import duckdb

from eim.data.backup_dbs import copy_db_cold, count_file

MIN_FREE = 0.30
MIN_BYTES = 256 * 2**20


class CompactError(RuntimeError):
    """La copia no cuadra o queda un WAL sin volcar: la base original no se toca."""


def _side(path: Path, suffix: str) -> Path:
    return path.with_name(path.name + suffix)


def usage(path: Path) -> tuple[int, int]:
    """(bloques totales, bloques libres) tras volcar el WAL al archivo. Lanza
    `duckdb.IOException` si otro proceso la tiene abierta."""
    con = duckdb.connect(str(path))
    try:
        con.execute("CHECKPOINT")
        total, free = con.execute(
            "SELECT total_blocks, free_blocks FROM pragma_database_size()").fetchone()
    finally:
        con.close()
    return int(total), int(free)


def compact(path: str | Path, min_free: float = MIN_FREE, min_bytes: int = MIN_BYTES
            ) -> dict | None:
    """Compacta si compensa; None si no hacía falta. `CompactError` si la copia no cuadra
    (el original queda intacto); `duckdb.IOException` si la base está en uso."""
    path = Path(path)
    old = _side(path, ".old")
    if old.exists() and not path.exists():   # cambio cortado a medias: se deshace
        old.replace(path)
    if not path.exists() or path.stat().st_size < min_bytes:
        return None
    total, free = usage(path)
    if not total or free / total < min_free:
        return None
    wal = _side(path, ".wal")
    if wal.exists() and wal.stat().st_size:
        raise CompactError(f"{wal.name} sin volcar: no se compacta")
    t0, before = time.monotonic(), path.stat().st_size
    tmp = path.with_name(path.stem + ".compact" + path.suffix)
    for f in (tmp, _side(tmp, ".wal")):
        f.unlink(missing_ok=True)
    try:
        want = count_file(path)
        got = copy_db_cold(path, tmp)
        if got != want:
            raise CompactError(f"la copia no cuadra: {want} → {got}")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    old.unlink(missing_ok=True)
    wal.unlink(missing_ok=True)
    path.replace(old)
    tmp.replace(path)
    old.unlink()
    return {"before_mb": round(before / 2**20), "after_mb": round(path.stat().st_size / 2**20),
            "free": round(free / total, 3), "tables": len(got),
            "seconds": round(time.monotonic() - t0, 1)}
