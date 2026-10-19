"""Identidad de la máquina (T61): quién generó cada fila de la experiencia compartida.

`data/machine_id` guarda un id estable (`<equipo>-<6 hex>`), creado una vez. `EIM_MACHINE`
(alias legible, p. ej. `juan-portatil`) lo reemplaza si se define: debe ser único entre los
colaboradores y no cambiarse después (es la carpeta de la nube y la procedencia de las filas).
Nunca es un secreto ni sale de la máquina más que como etiqueta.
"""

from __future__ import annotations

import os
import platform
import re
import secrets
from pathlib import Path

FILE = "machine_id"
_VALID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def clean(raw: str) -> str:
    """Etiqueta segura para nombre de carpeta: minúsculas, dígitos, `-` y `_`."""
    s = re.sub(r"[^a-z0-9_-]+", "-", raw.strip().lower()).strip("-_")
    return s[:40]


def machine_id(data_dir: str | Path, env: dict | None = None) -> str:
    """Id de esta máquina. Prioridad: `EIM_MACHINE`, `data/machine_id`, uno nuevo (se guarda)."""
    alias = clean((env if env is not None else os.environ).get("EIM_MACHINE", ""))
    if alias:
        if not _VALID.match(alias):
            raise ValueError(f"EIM_MACHINE inválido: {alias!r}")
        return alias
    path = Path(data_dir) / FILE
    try:
        got = clean(path.read_text(encoding="utf-8"))
    except OSError:
        got = ""
    if got:
        return got
    new = f"{clean(platform.node()) or 'equipo'}-{secrets.token_hex(3)}"[:40]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new + "\n", encoding="utf-8")
    return new


def add_machine_column(con, table: str, machine: str) -> bool:
    """Migración idempotente: `machine` en una tabla sin clave natural, rellena con el id
    local las filas previas. True si hizo la migración."""
    cols = {r[0] for r in con.execute(
        "SELECT column_name FROM duckdb_columns() WHERE table_name = ?", [table]).fetchall()}
    if not cols or "machine" in cols:
        return False
    con.execute(f'ALTER TABLE "{table}" ADD COLUMN machine VARCHAR')
    con.execute(f'UPDATE "{table}" SET machine = ?', [machine])
    return True
