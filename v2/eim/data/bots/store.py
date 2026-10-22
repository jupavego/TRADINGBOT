"""Tabla `bot_signals` (DuckDB, misma conexión que `ReportStore`): posturas point-in-time.

Solo se añade, nunca se reescribe: la clave es (bot, estrategia, versión, símbolo, marco, asof) y
un duplicado se ignora (la primera escritura manda). Cada fila lleva `asof` (hasta qué dato se
calculó), la versión (SHA + parámetros) y el estado; `created_ms` es cuándo se guardó. Una señal con
`asof` en el futuro respecto del reloj de guardado se rechaza.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Iterable
from dataclasses import dataclass

from eim.core import BotSignal

_DDL = """
CREATE TABLE IF NOT EXISTS bot_signals (
    bot_id VARCHAR, strategy VARCHAR, version VARCHAR, symbol VARCHAR, timeframe VARCHAR,
    asof_ms BIGINT, stance DOUBLE, confidence DOUBLE, status VARCHAR, created_ms BIGINT,
    signal VARCHAR,
    PRIMARY KEY (bot_id, strategy, version, symbol, timeframe, asof_ms)
)
"""
BATCH = 500


@dataclass(frozen=True, slots=True)
class LeanSignal:
    """Lo que la puntuación lee de una postura (sin `raw`/`evidence`/`data_quality`)."""

    bot_id: str
    strategy: str
    version: str
    symbol: str
    timeframe: str
    asof: int
    stance: float
    confidence: float | None
    status: str
    horizon_bars: int | None

_COLS = "bot_id, strategy, version, symbol, timeframe, asof_ms, stance, confidence, status, " \
        "created_ms, signal"


class BotSignalStore:
    """Comparte conexión y candado con `ReportStore` (ver `ReportStore.connection`)."""

    def __init__(self, con, lock: threading.Lock) -> None:
        self._con, self._lock = con, lock
        with lock:
            con.execute(_DDL)

    def append(self, sig: BotSignal, created_ms: int) -> bool:
        """Guarda la señal; False si ya había una igual en la clave (no se sobrescribe)."""
        if sig.asof > created_ms:
            raise ValueError(f"asof {sig.asof} posterior al momento de guardar {created_ms}")
        with self._lock:
            (inserted,) = self._con.execute(
                f"INSERT INTO bot_signals ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT DO NOTHING",
                [sig.bot_id, sig.strategy, sig.version, sig.symbol, sig.timeframe, sig.asof,
                 sig.stance, sig.confidence, sig.status, created_ms,
                 sig.model_dump_json()]).fetchone()
        return bool(inserted)

    def append_many(self, sigs: Iterable[BotSignal], created_ms: int) -> int:
        """Guarda por lotes (una transacción por lote); devuelve las filas nuevas.

        Mismo contrato que `append`: la primera escritura manda y una `asof` posterior a
        `created_ms` se rechaza, aquí antes de insertar nada."""
        rows = []
        for sig in sigs:
            if sig.asof > created_ms:
                raise ValueError(f"asof {sig.asof} posterior al momento de guardar {created_ms}")
            rows.append([sig.bot_id, sig.strategy, sig.version, sig.symbol, sig.timeframe,
                         sig.asof, sig.stance, sig.confidence, sig.status, created_ms,
                         sig.model_dump_json()])
        added = 0
        with self._lock:
            for i in range(0, len(rows), BATCH):
                before = self._con.execute("SELECT count(*) FROM bot_signals").fetchone()[0]
                self._con.execute("BEGIN")
                try:
                    chunk = rows[i:i + BATCH]
                    self._con.execute(
                        f"INSERT INTO bot_signals ({_COLS}) VALUES "
                        + ",".join(["(?,?,?,?,?,?,?,?,?,?,?)"] * len(chunk))
                        + " ON CONFLICT DO NOTHING", [x for r in chunk for x in r])
                    self._con.execute("COMMIT")
                except Exception:
                    self._con.execute("ROLLBACK")
                    raise
                after = self._con.execute("SELECT count(*) FROM bot_signals").fetchone()[0]
                added += after - before
        return added

    def query(self, symbol: str, timeframe: str, start: int | None = None,
              end: int | None = None, bot_id: str | None = None,
              limit: int = 1000) -> list[BotSignal]:
        """Señales por `asof` ascendente (las más recientes si hay más de `limit`)."""
        q, args = "SELECT signal FROM bot_signals WHERE symbol = ? AND timeframe = ?", \
            [symbol, timeframe]
        for clause, val in ((" AND asof_ms >= ?", start), (" AND asof_ms <= ?", end),
                            (" AND bot_id = ?", bot_id)):
            if val is not None:
                q, args = q + clause, [*args, val]
        q += f" ORDER BY asof_ms DESC, bot_id, strategy LIMIT {int(limit)}"
        with self._lock:
            rows = self._con.execute(q, args).fetchall()
        return [BotSignal.model_validate_json(r[0]) for r in reversed(rows)]

    def last_version(self, bot_id: str, strategy: str, symbol: str, timeframe: str,
                     before: int) -> str | None:
        """Versión de la última señal guardada de esa estrategia con `asof` < `before`."""
        with self._lock:
            row = self._con.execute(
                "SELECT version FROM bot_signals WHERE bot_id = ? AND strategy = ? AND "
                "symbol = ? AND timeframe = ? AND asof_ms < ? ORDER BY asof_ms DESC LIMIT 1",
                [bot_id, strategy, symbol, timeframe, before]).fetchone()
        return row[0] if row else None

    def query_all(self, symbol: str, timeframe: str, end: int | None = None
                  ) -> list[tuple[BotSignal, int]]:
        """Todas las señales (hasta `end`) con el momento en que se guardaron (T59): distingue lo
        decidido en vivo de lo rellenado después. Por `asof` ascendente."""
        q, args = ("SELECT signal, created_ms FROM bot_signals WHERE symbol = ? AND "
                   "timeframe = ?"), [symbol, timeframe]
        if end is not None:
            q, args = q + " AND asof_ms <= ?", [*args, end]
        with self._lock:
            rows = self._con.execute(q + " ORDER BY asof_ms, bot_id, strategy", args).fetchall()
        return [(BotSignal.model_validate_json(r[0]), int(r[1])) for r in rows]

    def query_lean(self, symbol: str, timeframe: str, end: int | None = None
                   ) -> list[tuple[LeanSignal, int]]:
        """Como `query_all`, pero solo con lo que usa la puntuación (identidad, `asof`, postura,
        confianza, horizonte, estado). Sin `raw`/`evidence`/`data_quality`: ~10× menos memoria.
        Devuelve `LeanSignal` (mismos campos, sin pydantic): no sirve para mostrar ni guardar."""
        q, args = ("SELECT bot_id, strategy, version, symbol, timeframe, asof_ms, stance, "
                   "confidence, status, created_ms, "
                   "try_cast(json_extract_string(signal, '$.horizon_bars') AS INTEGER) "
                   "FROM bot_signals WHERE symbol = ? AND timeframe = ?"), [symbol, timeframe]
        if end is not None:
            q, args = q + " AND asof_ms <= ?", [*args, end]
        with self._lock:
            cur = self._con.execute(q + " ORDER BY asof_ms, bot_id, strategy", args)
            rows = cur.fetchall()
        out = []
        for r in rows:
            sig = LeanSignal(*(sys.intern(x) if isinstance(x, str) else x for x in r[:9]),
                             None if r[10] is None else int(r[10]))
            out.append((sig, int(r[9])))
        return out
