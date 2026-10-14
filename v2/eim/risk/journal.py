"""Registro persistente de decisiones de riesgo (DuckDB, misma conexión que `ReportStore`)."""

from __future__ import annotations

import hashlib
import json
import threading

from eim.risk.models import RiskDecision

_DDL = """
CREATE TABLE IF NOT EXISTS risk_decisions (
    id VARCHAR PRIMARY KEY, symbol VARCHAR, timeframe VARCHAR, plan_id VARCHAR,
    asof_ms BIGINT, decided_at BIGINT, approved BOOLEAN, decision VARCHAR
)
"""


def decision_id(d: RiskDecision) -> str:
    """Una fila por resultado distinto de un plan: reevaluar con el mismo resultado solo
    actualiza la hora; un cambio (p. ej. aprobado → vetado) queda como fila nueva."""
    outcome = hashlib.sha256(json.dumps([d.approved, d.reasons, round(d.size, 12)])
                             .encode()).hexdigest()[:16]
    return f"{d.symbol}:{d.timeframe}:{d.plan_id}:{d.asof}:{d.config_version}:{outcome}"


class RiskJournal:
    def __init__(self, con, lock: threading.Lock) -> None:
        self._con, self._lock = con, lock
        with lock:
            con.execute(_DDL)

    def __call__(self, d: RiskDecision) -> None:
        row = [decision_id(d), d.symbol, d.timeframe, d.plan_id, d.asof, d.decided_at,
               d.approved, d.model_dump_json()]
        with self._lock:
            self._con.execute("DELETE FROM risk_decisions WHERE id = ?", [row[0]])
            self._con.execute("INSERT INTO risk_decisions VALUES (?,?,?,?,?,?,?,?)", row)

    def query(self, symbol: str, timeframe: str, limit: int = 200) -> list[RiskDecision]:
        with self._lock:
            rows = self._con.execute(
                "SELECT decision FROM risk_decisions WHERE symbol = ? AND timeframe = ? "
                "ORDER BY asof_ms DESC, decided_at DESC LIMIT ?", [symbol, timeframe, limit]
            ).fetchall()
        return [RiskDecision.model_validate_json(r[0]) for r in rows]

    def recent(self, since: int = 0, until: int | None = None, approved: bool | None = None,
               limit: int = 200) -> list[RiskDecision]:
        """Decisiones de todos los símbolos con `decided_at` en [since, until), recientes 1.º."""
        sql = "SELECT decision FROM risk_decisions WHERE decided_at >= ?"
        args: list = [since]
        if until is not None:
            sql, args = sql + " AND decided_at < ?", [*args, until]
        if approved is not None:
            sql, args = sql + " AND approved = ?", [*args, approved]
        with self._lock:
            rows = self._con.execute(f"{sql} ORDER BY decided_at DESC LIMIT {int(limit)}",
                                     args).fetchall()
        return [RiskDecision.model_validate_json(r[0]) for r in rows]
