"""Persistencia de `AgentReport` en DuckDB (base de bitácora y calibración)."""

from __future__ import annotations

import threading
from pathlib import Path

import duckdb

from eim.core import AgentReport

_DDL = """
CREATE TABLE IF NOT EXISTS reports (
    symbol VARCHAR, timeframe VARCHAR, agent_id VARCHAR, version VARCHAR,
    asof_ms BIGINT, bias DOUBLE, confidence DOUBLE, status VARCHAR, report VARCHAR,
    PRIMARY KEY (symbol, timeframe, agent_id, version, asof_ms)
)
"""


class ReportStore:
    """Tabla `reports`; un reporte por (símbolo, marco, agente, versión, asof)."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(self._path)
        self._con.execute(_DDL)
        self._lock = threading.Lock()

    def save(self, symbol: str, timeframe: str, reports: list[AgentReport]) -> int:
        rows = [
            (symbol, timeframe, r.agent_id, r.version, r.asof, r.bias, r.confidence,
             r.status, r.model_dump_json())
            for r in reports
        ]
        with self._lock:
            self._con.executemany("INSERT OR REPLACE INTO reports VALUES (?,?,?,?,?,?,?,?,?)", rows)
        return len(rows)

    def query(
        self,
        symbol: str,
        timeframe: str,
        start: int | None = None,
        end: int | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[AgentReport]:
        """Reportes con `start <= asof < end`, más recientes primero."""
        where, params = ["symbol = ?", "timeframe = ?"], [symbol, timeframe]
        filters = (("asof_ms >= ?", start), ("asof_ms < ?", end), ("agent_id = ?", agent_id))
        for cond, val in filters:
            if val is not None:
                where.append(cond)
                params.append(val)
        q = (f"SELECT report FROM reports WHERE {' AND '.join(where)} "
             f"ORDER BY asof_ms DESC, agent_id LIMIT {int(limit)}")
        with self._lock:
            rows = self._con.execute(q, params).fetchall()
        return [AgentReport.model_validate_json(r[0]) for r in rows]

    def latest(self, symbol: str, timeframe: str) -> list[AgentReport]:
        """Los reportes del último `asof` de cada agente."""
        q = ("SELECT report FROM reports WHERE symbol = ? AND timeframe = ? "
             "QUALIFY row_number() OVER "
             "(PARTITION BY agent_id ORDER BY asof_ms DESC, version DESC) = 1 "
             "ORDER BY agent_id")
        with self._lock:
            rows = self._con.execute(q, [symbol, timeframe]).fetchall()
        return [AgentReport.model_validate_json(r[0]) for r in rows]

    @property
    def connection(self):
        """(conexión, cerrojo) compartidos con el libro de operaciones."""
        return self._con, self._lock

    def at(self, symbol: str, timeframe: str, asof: int) -> list[AgentReport]:
        """El último reporte de cada agente con `asof_ms <= asof` (estado en un instante)."""
        q = ("SELECT report FROM reports WHERE symbol = ? AND timeframe = ? AND asof_ms <= ? "
             "QUALIFY row_number() OVER "
             "(PARTITION BY agent_id ORDER BY asof_ms DESC, version DESC) = 1 "
             "ORDER BY agent_id")
        with self._lock:
            rows = self._con.execute(q, [symbol, timeframe, asof]).fetchall()
        return [AgentReport.model_validate_json(r[0]) for r in rows]

    def asofs(self, symbol: str, timeframe: str, limit: int = 2000) -> list[int]:
        """Instantes distintos con reportes, ascendentes (los últimos `limit`)."""
        with self._lock:
            rows = self._con.execute(
                "SELECT DISTINCT asof_ms FROM reports WHERE symbol = ? AND timeframe = ? "
                f"ORDER BY asof_ms DESC LIMIT {int(limit)}", [symbol, timeframe]).fetchall()
        return sorted(r[0] for r in rows)

    def close(self) -> None:
        with self._lock:
            self._con.close()
