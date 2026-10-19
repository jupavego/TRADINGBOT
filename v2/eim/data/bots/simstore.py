"""Tabla `bot_sim_runs` (DuckDB, misma conexión que `ReportStore`): corridas simuladas.

Solo se añade: la clave es (bot, estrategia, versión, símbolo, marco, inicio, fin) y un duplicado se
ignora. La corrida entera va como JSON (`run`); las columnas sueltas sirven para listar y filtrar.
"""

from __future__ import annotations

import threading

from eim.core import SimRun

_DDL = """
CREATE TABLE IF NOT EXISTS bot_sim_runs (
    bot_id VARCHAR, strategy VARCHAR, version VARCHAR, symbol VARCHAR, timeframe VARCHAR,
    start_ms BIGINT, end_ms BIGINT, status VARCHAR, n_fills INTEGER, created_ms BIGINT,
    run VARCHAR,
    PRIMARY KEY (bot_id, strategy, version, symbol, timeframe, start_ms, end_ms)
)
"""


class SimRunStore:
    def __init__(self, con, lock: threading.Lock) -> None:
        self._con, self._lock = con, lock
        with lock:
            con.execute(_DDL)

    def append(self, run: SimRun, created_ms: int) -> bool:
        """Guarda la corrida; False si ya había una igual en la clave (no se sobrescribe)."""
        if run.end > created_ms:
            raise ValueError(f"la ventana termina ({run.end}) después de guardar ({created_ms})")
        with self._lock:
            (inserted,) = self._con.execute(
                "INSERT INTO bot_sim_runs VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                [run.bot_id, run.strategy, run.version, run.symbol, run.timeframe, run.start,
                 run.end, run.status, len(run.fills), created_ms,
                 run.model_dump_json()]).fetchone()
        return bool(inserted)

    def query(self, bot_id: str | None = None, symbol: str | None = None,
              limit: int = 50) -> list[SimRun]:
        q, args, cl = "SELECT run FROM bot_sim_runs", [], []
        for col, val in (("bot_id", bot_id), ("symbol", symbol)):
            if val is not None:
                cl.append(f"{col} = ?")
                args.append(val)
        if cl:
            q += " WHERE " + " AND ".join(cl)
        q += f" ORDER BY end_ms DESC, bot_id, strategy LIMIT {int(limit)}"
        with self._lock:
            rows = self._con.execute(q, args).fetchall()
        return [SimRun.model_validate_json(r[0]) for r in rows]
