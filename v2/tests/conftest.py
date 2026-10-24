"""Entorno fijo para toda la suite: el gate da lo mismo en cualquier equipo (T74, T116).

- Ninguna prueba hereda el entorno del equipo: se retiran todas las variables `EIM_*` (alias
  `EIM_MACHINE`, LLM local, carpetas de datos, servicios…) antes de importar ninguna prueba. Las
  que activan a propósito una prueba opcional se guardan antes en `tests/opt_in.py`.
- `EIM_OBS=off`: los tests no escriben eventos del observatorio en `data/obs/spool`; los de
  `tests/observability/` lo encienden con su propia carpeta temporal (su `conftest.py`).
- DuckDB con memoria e hilos fijos, los de producción (`eim/data/duck.py`: 1 GB, 2 hilos): no
  depende de la RAM libre ni de lo que el equipo tenga en `EIM_DUCKDB_*`.
- `EIM_NOTIFY=0`: ningún supervisor de prueba lanza avisos de escritorio en Windows.
- Sin red: solo el bucle local (`tests/offline.py`); el resultado no depende de la conexión.
"""
from __future__ import annotations

import os

import tests.opt_in  # noqa: F401 — copia las variables opcionales antes de limpiar
from tests.offline import block_network

for _k in [k for k in os.environ if k.upper().startswith("EIM_")]:
    del os.environ[_k]
os.environ.update({"EIM_OBS": "off", "EIM_NOTIFY": "0",
                   "EIM_DUCKDB_MEMORY": "1GB", "EIM_DUCKDB_THREADS": "2"})
os.environ.pop("ANTHROPIC_API_KEY", None)  # la suite nunca llama al LLM real
block_network()
