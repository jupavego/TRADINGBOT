"""Historial de capital de la operación continua y estado de cuenta derivado de él.

Sin este historial el motor de riesgo veía «inicio de día = capital actual» y las reglas de
pérdida diaria/semanal y el drawdown no detectaban nada (pendiente anotado en T30).
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

from eim.execution.service import CLOSED, LiveTrade
from eim.risk.inputs import _day0, _week0
from eim.risk.models import AccountState

_DDL = """
CREATE TABLE IF NOT EXISTS op_equity (
    t BIGINT, mode VARCHAR, equity DOUBLE, PRIMARY KEY (mode, t)
)
"""


class EquityBook:
    """Tabla `op_equity` (misma conexión DuckDB que `ReportStore`), una fila por ciclo."""

    def __init__(self, con, lock: threading.Lock, mode: str) -> None:
        self._con, self._lock, self.mode = con, lock, mode
        with lock:
            con.execute(_DDL)

    def record(self, t: int, equity: float) -> None:
        with self._lock:
            self._con.execute("INSERT OR REPLACE INTO op_equity VALUES (?,?,?)",
                              [t, self.mode, equity])

    def series(self, since: int = 0, until: int | None = None) -> list[tuple[int, float]]:
        sql, args = "SELECT t, equity FROM op_equity WHERE mode = ? AND t >= ?", [self.mode, since]
        if until is not None:
            sql, args = sql + " AND t < ?", [*args, until]
        with self._lock:
            rows = self._con.execute(sql + " ORDER BY t", args).fetchall()
        return [(int(t), float(e)) for t, e in rows]

    def start_at(self, t: int) -> float | None:
        """Capital al instante `t`: último registro previo o, si la operación empezó después,
        el primero registrado (None sin historial)."""
        with self._lock:
            row = self._con.execute(
                "SELECT equity FROM op_equity WHERE mode = ? AND t < ? ORDER BY t DESC LIMIT 1",
                [self.mode, t]).fetchone() or self._con.execute(
                "SELECT equity FROM op_equity WHERE mode = ? ORDER BY t LIMIT 1",
                [self.mode]).fetchone()
        return float(row[0]) if row else None

    def peak(self) -> float | None:
        with self._lock:
            row = self._con.execute("SELECT max(equity) FROM op_equity WHERE mode = ?",
                                    [self.mode]).fetchone()
        return float(row[0]) if row and row[0] is not None else None


def drawdown(equity: float, peak: float | None) -> float:
    return 0.0 if not peak or peak <= 0 else max(0.0, (peak - equity) / peak)


def loss_streak(trades: Iterable[LiveTrade]) -> tuple[int, int | None]:
    """Pérdidas seguidas al final (por cierre) y hora de la última pérdida."""
    closed = sorted((t for t in trades if t.status == CLOSED and t.pnl is not None),
                    key=lambda t: t.closed_at or 0)
    streak, last = 0, None
    for t in closed:
        if (t.pnl or 0.0) < 0:
            streak, last = streak + 1, t.closed_at
        else:
            streak = 0
    return streak, last


def account_state(equity: float, now: int, book: EquityBook | None,
                  trades: Iterable[LiveTrade], open_symbols: tuple[str, ...],
                  source: str) -> AccountState:
    """Cuenta para el motor de riesgo: inicio de día/semana (UTC) y pico desde el historial."""
    trades = list(trades)
    streak, last_loss = loss_streak(trades)
    if book is None:
        day = week = peak = equity
    else:
        day = book.start_at(_day0(now)) or equity
        week = book.start_at(_week0(now)) or equity
        peak = max(book.peak() or equity, equity)
        source += " · historial de capital propio"
    return AccountState(equity=equity, day_start_equity=day, week_start_equity=week,
                        peak_equity=peak, open_symbols=open_symbols,
                        consecutive_losses=streak, last_loss_t=last_loss, source=source)
