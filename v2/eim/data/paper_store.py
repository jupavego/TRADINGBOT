"""Persistencia del bróker simulado (T47): contextos por vela en `data/paper.duckdb`.

Base aparte de `reports.duckdb`: el laboratorio de papel se puede borrar o regenerar sin tocar
los reportes en vivo. Un contexto por (símbolo, marco, asof); `origin` dice si se decidió en
tiempo real (`vivo`) o se reconstruyó después (`backtest`).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import duckdb

_DDL = """
CREATE TABLE IF NOT EXISTS paper_ctx (
    symbol VARCHAR, timeframe VARCHAR, asof_ms BIGINT, origin VARCHAR, version INTEGER,
    created_ms BIGINT, ctx VARCHAR, PRIMARY KEY (symbol, timeframe, asof_ms)
)
"""


class PaperStore:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(self._path)
        self._con.execute(_DDL)
        self._lock = threading.Lock()

    def save(self, symbol: str, timeframe: str, ctx: dict, origin: str, created_ms: int) -> None:
        row = (symbol, timeframe, int(ctx["t"]), origin, int(ctx.get("v", 1)), created_ms,
               json.dumps(ctx, separators=(",", ":")))
        with self._lock:
            self._con.execute("INSERT OR REPLACE INTO paper_ctx VALUES (?,?,?,?,?,?,?)", row)

    def asofs(self, symbol: str, timeframe: str) -> set[int]:
        with self._lock:
            rows = self._con.execute(
                "SELECT asof_ms FROM paper_ctx WHERE symbol = ? AND timeframe = ?",
                [symbol, timeframe]).fetchall()
        return {int(r[0]) for r in rows}

    def load(self, symbol: str, timeframe: str, start: int | None = None) -> list[dict]:
        """Contextos ascendentes; cada uno con su `origin`."""
        q = ("SELECT ctx, origin FROM paper_ctx WHERE symbol = ? AND timeframe = ?"
             + (" AND asof_ms >= ?" if start is not None else "") + " ORDER BY asof_ms")
        params: list = [symbol, timeframe] + ([start] if start is not None else [])
        with self._lock:
            rows = self._con.execute(q, params).fetchall()
        out = []
        for raw, origin in rows:
            d = json.loads(raw)
            d["origin"] = origin
            out.append(d)
        return out

    def stamp(self, symbol: str, timeframe: str) -> tuple[int, int | None]:
        """(cantidad, último asof): cambia cuando hay contextos nuevos."""
        with self._lock:
            n, last = self._con.execute(
                "SELECT count(*), max(asof_ms) FROM paper_ctx WHERE symbol = ? AND timeframe = ?",
                [symbol, timeframe]).fetchone()
        return int(n), None if last is None else int(last)

    def counts(self, symbol: str, timeframe: str) -> dict[str, int]:
        with self._lock:
            rows = self._con.execute(
                "SELECT origin, count(*) FROM paper_ctx WHERE symbol = ? AND timeframe = ? "
                "GROUP BY origin", [symbol, timeframe]).fetchall()
        return {str(o): int(n) for o, n in rows}

    def execute(self, sql: str, params: list | tuple = ()) -> list[tuple]:
        """SQL sobre la misma conexión (otras tablas del laboratorio, p. ej. la validación T49:
        DuckDB admite un solo proceso escritor, así que se comparte conexión y candado)."""
        with self._lock:
            return self._con.execute(sql, list(params)).fetchall()

    def executemany(self, sql: str, rows: list[tuple]) -> None:
        if rows:
            with self._lock:
                self._con.executemany(sql, rows)

    def close(self) -> None:
        with self._lock:
            self._con.close()
