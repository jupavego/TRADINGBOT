"""Ajuste común de las conexiones DuckDB persistentes (memoria acotada).

Por defecto DuckDB toma hasta el 80 % de la RAM *total*; en un equipo con poca RAM libre eso
no protege nada y las consultas grandes mueren con `Out of Memory Error` en vez de derramar a
disco. Aquí se fija un tope (por defecto 1 GB, `EIM_DUCKDB_MEMORY`) y 2 hilos
(`EIM_DUCKDB_THREADS`); lo que no quepa se derrama al directorio temporal de DuckDB.
"""

from __future__ import annotations

import os

DEFAULT_MEMORY = "1GB"
DEFAULT_THREADS = 2


def tune(con) -> None:
    con.execute("SET memory_limit = ?", [os.environ.get("EIM_DUCKDB_MEMORY", DEFAULT_MEMORY)])
    con.execute("SET threads = ?", [int(os.environ.get("EIM_DUCKDB_THREADS", DEFAULT_THREADS))])
