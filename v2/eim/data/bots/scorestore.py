"""Tabla `bot_scorecard` (DuckDB, misma conexión que `ReportStore`): tablas de puntuación T59.

Solo se añade: la clave es (símbolo, criterios, asof). Cada fila guarda el JSON completo de
`eim.bots.scorecard.score` (estados, dimensiones, veredictos de la puerta, intentos y régimen).
"""

from __future__ import annotations

import json
import threading

_DDL = """
CREATE TABLE IF NOT EXISTS bot_scorecard (
    symbol VARCHAR, criteria VARCHAR, asof_ms BIGINT, created_ms BIGINT, payload VARCHAR,
    PRIMARY KEY (symbol, criteria, asof_ms)
)
"""


class ScoreStore:
    def __init__(self, con, lock: threading.Lock) -> None:
        self._con, self._lock = con, lock
        with lock:
            con.execute(_DDL)

    def save(self, payload: dict, created_ms: int) -> bool:
        """Guarda la tabla; False si ya había una con el mismo `asof` (no se sobrescribe)."""
        with self._lock:
            (inserted,) = self._con.execute(
                "INSERT INTO bot_scorecard VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
                [payload["symbol"], payload["criteria"]["version"], payload["asof"], created_ms,
                 json.dumps(payload, separators=(",", ":"))]).fetchone()
        return bool(inserted)

    def latest(self, symbol: str, criteria: str | None = None) -> dict | None:
        q = "SELECT payload, created_ms FROM bot_scorecard WHERE symbol = ?"
        args: list = [symbol]
        if criteria is not None:
            q, args = q + " AND criteria = ?", [*args, criteria]
        with self._lock:
            row = self._con.execute(q + " ORDER BY asof_ms DESC LIMIT 1", args).fetchone()
        if row is None:
            return None
        return {**json.loads(row[0]), "computed": int(row[1])}

    def history(self, symbol: str, limit: int = 50) -> list[dict]:
        """Estados por corrida (más recientes primero), sin el detalle."""
        with self._lock:
            rows = self._con.execute(
                "SELECT payload, created_ms FROM bot_scorecard WHERE symbol = ? "
                "ORDER BY asof_ms DESC LIMIT ?", [symbol, int(limit)]).fetchall()
        out = []
        for raw, created in rows:
            d = json.loads(raw)
            out.append({"asof": d["asof"], "computed": int(created), "summary": d["summary"]})
        return out
