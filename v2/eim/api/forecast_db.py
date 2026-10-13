"""Persistencia de `ForecastSet` en DuckDB (insumo del seguimiento y calibración, T19)."""

from __future__ import annotations

import threading

from eim.core import ForecastSet

_DDL = """
CREATE TABLE IF NOT EXISTS forecasts (
    symbol VARCHAR, timeframe VARCHAR, made_at BIGINT, horizon INTEGER, engine VARCHAR,
    forecast VARCHAR, PRIMARY KEY (symbol, timeframe, made_at, horizon, engine)
)
"""


class ForecastStore:
    """Tabla `forecasts`; comparte conexión con `ReportStore` (ver `ReportStore.connection`)."""

    def __init__(self, con, lock: threading.Lock) -> None:
        self._con, self._lock = con, lock
        with lock:
            con.execute(_DDL)

    def save(self, fs: ForecastSet) -> None:
        with self._lock:
            self._con.execute(
                "INSERT OR REPLACE INTO forecasts VALUES (?,?,?,?,?,?)",
                [fs.symbol, fs.timeframe, fs.made_at, fs.horizon_bars, fs.engine,
                 fs.model_dump_json()])

    def query(self, symbol: str, timeframe: str, limit: int = 50) -> list[ForecastSet]:
        """Pronósticos más recientes primero."""
        with self._lock:
            rows = self._con.execute(
                "SELECT forecast FROM forecasts WHERE symbol = ? AND timeframe = ? "
                f"ORDER BY made_at DESC LIMIT {int(limit)}", [symbol, timeframe]).fetchall()
        return [ForecastSet.model_validate_json(r[0]) for r in rows]

    def horizon_all(self, symbol: str, timeframe: str, horizon: int) -> list[ForecastSet]:
        """Todos los pronósticos de un horizonte, por `made_at` ascendente (para evaluar)."""
        with self._lock:
            rows = self._con.execute(
                "SELECT forecast FROM forecasts WHERE symbol = ? AND timeframe = ? AND horizon = ? "
                "ORDER BY made_at", [symbol, timeframe, horizon]).fetchall()
        return [ForecastSet.model_validate_json(r[0]) for r in rows]
