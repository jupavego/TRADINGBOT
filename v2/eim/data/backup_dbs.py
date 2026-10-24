"""Las bases de la copia de seguridad (T115): cuáles entran, dónde viven y por qué camino se
copia cada una. Lo usan `eim.data.backup` (crear) y `eim.data.backup_restore` (verificar,
restaurar).

| base | la tiene abierta | copia en caliente |
|---|---|---|
| `reports.duckdb` | la API | su conexión (`ReportStore.connection`), entre ciclos de operación |
| `paper.duckdb` | la API | su conexión (`PaperStore.connection`) |
| `obs.duckdb` (derivado, T73) | la API | la conexión del observatorio |
| `leaders.duckdb` | el servicio de líderes | instantánea pedida al servicio (`request_snapshot`) |

Si nadie la usa, cada base se copia en frío (adjuntada en solo lectura). Una base en uso que no
se puede pedir a su dueño no rompe la copia: queda *ausente con motivo* en el manifiesto.
"""

from __future__ import annotations

import hashlib
import shutil
import time
import uuid
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path

import duckdb

from eim.data.leader_snapshot import WAIT_S, request_snapshot, wait_snapshot

DB_NAME = "reports.duckdb"
PAPER = "paper.duckdb"
LEADERS = "leaders.duckdb"
OBS_NAME = "obs.duckdb"
# nombre dentro de la copia → ruta bajo `data/` (el observatorio vive en `obs/`)
DBS = {DB_NAME: DB_NAME, PAPER: PAPER, LEADERS: LEADERS, OBS_NAME: f"obs/{OBS_NAME}"}
API_DBS = (DB_NAME, PAPER, OBS_NAME)        # las abre la API cuando está en marcha
# Instantánea de leaders.duckdb: medida en vivo el 2026-10-24, 454 MB en 278 s (en frío, 26 s);
# se espera mientras avance (`leader_snapshot.wait_snapshot`), con este tope total.
LEADERS_WAIT_S = WAIT_S
HOT, COLD, SNAP = "caliente", "frío", "instantánea del servicio de líderes"


class BackupError(RuntimeError):
    pass


class DbBusy(BackupError):
    """La base está abierta por otro proceso (o por este): hay que pedírsela a su dueño."""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sql_path(p: Path) -> str:
    """Literal SQL de una ruta (ATTACH no admite parámetros): comillas simples duplicadas."""
    return "'" + p.as_posix().replace("'", "''") + "'"


def tables(con) -> dict[str, int]:
    names = [r[0] for r in con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE database_name = current_database() "
        "ORDER BY table_name").fetchall()]
    return {n: con.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0] for n in names}


def count_file(p: Path) -> dict[str, int]:
    """Filas por tabla de un archivo de base (solo lectura)."""
    con = duckdb.connect(str(p), read_only=True)
    try:
        return tables(con)
    finally:
        con.close()


def _busy(e: duckdb.Error) -> bool:
    """¿El ATTACH falló porque otro proceso (IOException del cerrojo) o este mismo (Binder) la
    tiene abierta? Si no, el archivo está dañado o es incompatible."""
    return isinstance(e, duckdb.BinderException) or (
        isinstance(e, duckdb.IOException) and "not a valid DuckDB database" not in str(e))


def in_use(src: Path) -> str | None:
    """Motivo si otro proceso (o este) tiene la base abierta; None si está libre (o dañada)."""
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH {sql_path(src)} AS probe (READ_ONLY)")
    except duckdb.Error as e:
        return str(e) if _busy(e) else None
    finally:
        con.close()
    return None


def copy_db_hot(con, lock, dst: Path) -> dict[str, int]:
    """Copia coherente desde la conexión abierta del proceso dueño. El cerrojo de los
    escritores solo se toma para abrir un cursor propio: la copia es UNA sentencia (una
    transacción, instantánea MVCC de DuckDB), así que es coherente y los escritores no esperan.
    Las filas se cuentan en la copia."""
    with lock or nullcontext():
        cur = con.cursor()
    alias = "eim_backup_" + uuid.uuid4().hex[:12]   # dos copias a la vez no chocan
    try:
        src = cur.execute("SELECT current_database()").fetchone()[0]
        cur.execute(f"ATTACH {sql_path(dst)} AS {alias}")
        try:
            cur.execute(f'COPY FROM DATABASE "{src}" TO {alias}')
        finally:
            cur.execute(f"DETACH {alias}")
    finally:
        cur.close()
    return count_file(dst)


def copy_db_cold(src: Path, dst: Path) -> dict[str, int]:
    """Copia de una base que nadie usa. En uso (hay que pedírsela a su dueño) o dañada →
    BackupError con el motivo."""
    con = duckdb.connect()
    try:
        try:
            con.execute(f"ATTACH {sql_path(src)} AS src (READ_ONLY)")
        except duckdb.Error as e:
            if _busy(e):
                raise DbBusy(f"en uso por otro proceso: {e}") from e
            raise BackupError(f"no se puede abrir (¿dañada?): {e}") from e
        con.execute(f"ATTACH {sql_path(dst)} AS eim_backup")
        con.execute("COPY FROM DATABASE src TO eim_backup")
    finally:
        con.close()
    return count_file(dst)


def copy_leaders_snapshot(data_dir: Path, dst: Path, wait_s: float = LEADERS_WAIT_S,
                          sleep: Callable[[float], None] = time.sleep,
                          now_ms: Callable[[], int] = lambda: int(time.time() * 1000)
                          ) -> dict[str, int]:
    """`leaders.duckdb` en uso: el servicio de líderes hace la instantánea en su proceso (cursor
    propio, sin parar la captura, ver `LeaderStore.snapshot`) y aquí solo se espera y se mueve.
    Sin avance o pasado `wait_s` → BackupError (la base queda ausente con motivo)."""
    snap = request_snapshot(data_dir, now_ms())
    try:
        wait_snapshot(data_dir, snap, wait_s, sleep)
    except TimeoutError as e:
        raise BackupError(f"en uso por otro proceso y el servicio de líderes {e}") from e
    shutil.move(snap, dst)          # aparece completa: el servicio la escribe aparte y renombra
    return count_file(dst)


def copy_db(name: str, data_dir: Path, dst: Path, live: tuple | None, *,
            leaders_wait_s: float = LEADERS_WAIT_S,
            sleep: Callable[[float], None] = time.sleep) -> tuple[dict[str, int], str] | None:
    """(filas por tabla, camino) de una base; None si no existe en este equipo. En uso sin forma
    de pedírsela a su dueño (`DbBusy`), o dañada → BackupError con el motivo."""
    if live is not None:
        return copy_db_hot(*live, dst), HOT
    src = data_dir / DBS[name]
    if not src.exists():
        return None
    try:
        return copy_db_cold(src, dst), COLD
    except DbBusy:
        if name != LEADERS:
            raise
    return copy_leaders_snapshot(data_dir, dst, leaders_wait_s, sleep), SNAP
