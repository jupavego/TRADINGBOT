"""Servicio supervisado: bucle de ciclos con latido, reintento con espera creciente y registro.

Dos niveles de reinicio automático:
1. Dentro del proceso (`Supervisor.run`): un ciclo que lanza una excepción no mata el bucle;
   se registra, se avisa (alerta «servicio» tras fallos seguidos) y se reintenta con espera
   exponencial (tope `max_backoff_s`).
2. Fuera del proceso (`eim.operation.watchdog`): relanza la API si muere o si el latido
   (`data/operation/heartbeat.json`) deja de avanzar.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from eim.api.forecast import DEFAULT_HORIZON
from eim.api.forecast_db import ForecastStore
from eim.api.risk import RiskDesk
from eim.data import backup
from eim.execution.sim_broker import SimBroker
from eim.operation import report as report_io
from eim.operation import state, weekly
from eim.operation.alerts import (
    BACKUP,
    CRITICAL,
    INFO,
    REPORT,
    SERVICE,
    WARN,
    Alert,
    AlertCenter,
    Condition,
    Sink,
)
from eim.operation.cycle import CycleResult, OperationCycle, OperationParams
from eim.operation.equity import EquityBook
from eim.operation.notify import JsonLog, WindowsToast

FAILS_BEFORE_ALERT = 3
BACKUP_RETRY_MS = 3_600_000


def _now() -> int:
    return int(time.time() * 1000)


class Operation:
    """Componentes de la operación continua sobre la API ya montada (mismo proceso)."""

    def __init__(self, *, store, provider, reports, registry, desk: RiskDesk,
                 params: OperationParams, data_dir: Path, reports_dir: Path, edge_path: Path,
                 forecaster=None, bots=None, sinks: Iterable[Sink] | None = None,
                 backup_dir: Path | None = None, backup_keep: int = 14,
                 clock: Callable[[], int] = _now) -> None:
        con, lock = reports.connection
        rt = desk.rt
        self.mode = desk.mode.value
        self.desk, self.store, self.params, self.clock = desk, store, params, clock
        self.reports_dir, self.edge_path = reports_dir, edge_path
        self.root = data_dir / "operation"
        self.data_dir, self.backup_dir, self.backup_keep = data_dir, backup_dir, backup_keep
        self._db = (con, lock)
        self._step_lock = threading.RLock()
        self._backup_retry_at = 0          # tras un fallo, reintento espaciado (BACKUP_RETRY_MS)
        self.book = EquityBook(con, lock, self.mode) if rt.svc is not None else None
        rt.equity_book = self.book
        self.log = JsonLog(self.root / "logs", clock)
        chosen = [WindowsToast()] if sinks is None else list(sinks)
        self.alerts = AlertCenter(con, lock, [self.log.alert_sink, *chosen])
        self.forecasts = ForecastStore(con, lock)
        self.state_path = self.root / f"state_{self.mode.lower()}.json"
        self.cursors = state.load(self.state_path, rt.svc, self.mode)
        self.cycle = OperationCycle(store, provider, reports, registry, desk, self.book,
                                    self.alerts, self.log, params, self.cursors, forecaster,
                                    bots)
        self.status: dict = {"state": "iniciando", "mode": self.mode, "pid": os.getpid(),
                             "process_started_at": clock(), "cycles": 0, "failures": 0,
                             "consecutive_failures": 0, "last_heartbeat": None,
                             "last_error": "", "last_cycle": None, "next_cycle_at": None,
                             "poll_s": params.poll_s, "timeframe": params.timeframe,
                             "symbols": list(params.symbols)}
        self.log.write("servicio_iniciado", mode=self.mode, trades=len(rt.svc.trades)
                       if rt.svc else 0, cursors=self.cursors.to_json())

    # --- un paso (bloqueante: corre en un hilo) ----------------------------
    def step(self) -> CycleResult:
        with self._step_lock:       # una copia a demanda nunca ve un ciclo a medias
            now = self.clock()
            res = self.cycle.run(now)
            state.save(self.state_path, self.desk.rt.svc, self.cursors, self.mode)
            self.weekly_if_due(now)
            self.backup_if_due(now)
        row = res.to_json()
        row["cycle_t"] = row.pop("t")
        self.log.write("ciclo", "info" if res.ok else "warn", **row)
        return res

    def heartbeat(self) -> None:
        self.status["last_heartbeat"] = self.clock()
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / "heartbeat.tmp"
        tmp.write_text(json.dumps({k: self.status[k] for k in (
            "last_heartbeat", "pid", "state", "mode", "cycles", "consecutive_failures")}),
            encoding="utf-8")
        tmp.replace(self.root / "heartbeat.json")

    # --- informes -----------------------------------------------------------
    def fee_rate(self) -> float:
        svc = self.desk.rt.svc
        return svc.broker.fee_rate if svc and isinstance(svc.broker, SimBroker) else 0.0005

    def compose(self, t0: int, t1: int) -> dict:
        rt, tf, h = self.desk.rt, self.params.timeframe, DEFAULT_HORIZON
        calib = {}
        for s in self.params.symbols:
            fcs = [f for f in self.forecasts.horizon_all(s, tf, h) if t0 <= f.made_at < t1]
            closes = {c.t: c.c for c in self.store.read_candles(s, tf, t0)}
            calib[s] = weekly.calibration(fcs, closes, h)
        return weekly.compose(
            t0=t0, t1=t1, mode=self.mode, symbols=self.params.symbols,
            trades=list(rt.svc.trades.values()) if rt.svc else [], fee_rate=self.fee_rate(),
            equity=self.book.series(t0, t1) if self.book else [],
            alerts=self.alerts.recent(t0, t1, 1000), active_alerts=self.alerts.active,
            decisions=self.desk.journal.recent(t0, t1, limit=5000),
            edge=weekly.load_edge(self.edge_path), calib=calib,
            started_at=self.cursors.started_at)

    def write_report(self, t0: int, t1: int, name: str | None = None) -> dict:
        rep = self.compose(t0, t1)
        j, m = report_io.write(rep, self.reports_dir, name)
        self.log.write("informe", path=str(m))
        return {"json": str(j), "md": str(m), "report": rep}

    def weekly_if_due(self, now: int) -> None:
        """Al empezar una semana UTC se escribe el informe de la anterior (una vez)."""
        w0, _ = weekly.week_bounds(now)
        prev = w0 - weekly.WEEK_MS
        started = self.cursors.started_at
        if self.cursors.last_report_week == prev or started is None or started >= w0:
            return
        out = self.write_report(prev, w0)
        self.cursors.last_report_week = prev
        state.save(self.state_path, self.desk.rt.svc, self.cursors, self.mode)
        self.alerts.emit(Alert(now, REPORT, INFO, "Informe semanal listo", out["md"]))

    def backup_if_due(self, now: int) -> None:
        """Copia de seguridad diaria (UTC). Un fallo alerta (una vez) y se reintenta cada
        `BACKUP_RETRY_MS` (no en cada ciclo: la copia retiene el cerrojo de la base); nunca
        detiene la operación."""
        if (self.backup_dir is None or now < self._backup_retry_at
                or not backup.due_today(self.backup_dir, now / 1000)):
            return
        err = ""
        try:
            out = self.backup_now(clock=lambda: now / 1000)
            self.log.write("copia_seguridad", path=str(out))
        except Exception as e:  # noqa: BLE001 - se alerta y se sigue operando
            err = f"{type(e).__name__}: {e}"
            self._backup_retry_at = now + BACKUP_RETRY_MS
            self.log.write("copia_seguridad", "warn", error=err)
        self.alerts.update(now, [Condition("copia_seguridad", BACKUP, bool(err), WARN,
                                           "Copia de seguridad fallida", err)])

    def backup_now(self, with_market: bool = False, clock: Callable[[], float] = time.time):
        """Copia entre ciclos (base + estado del servicio consistentes entre sí)."""
        if self.backup_dir is None:
            raise RuntimeError("sin carpeta de copias")
        with self._step_lock:
            return backup.create(self.data_dir, self.backup_dir, con=self._db[0],
                                 lock=self._db[1], with_market=with_market,
                                 keep=self.backup_keep, clock=clock)


class Supervisor:
    def __init__(self, op: Operation, max_backoff_s: float = 300.0,
                 sleep: Callable[[float], object] = asyncio.sleep) -> None:
        self.op, self.max_backoff_s, self._sleep = op, max_backoff_s, sleep

    async def run(self, max_cycles: int | None = None) -> None:
        op, st = self.op, self.op.status
        st["state"] = "operando"
        n = 0
        while max_cycles is None or n < max_cycles:
            n += 1
            wait = op.params.poll_s
            try:
                res = await asyncio.to_thread(op.step)
                st.update(cycles=st["cycles"] + 1, consecutive_failures=0, state="operando",
                          last_cycle=res.to_json())
                if res.errors:
                    st["last_error"] = " · ".join(res.errors)[:500]
            except Exception as e:  # noqa: BLE001 - el bucle no debe morir
                st["failures"] += 1
                st["consecutive_failures"] += 1
                st["state"] = "reintentando"
                st["last_error"] = f"{type(e).__name__}: {e}"
                wait = min(self.max_backoff_s, op.params.poll_s * 2 ** st["consecutive_failures"])
                op.log.write("ciclo_fallido", "error", error=st["last_error"],
                             consecutive=st["consecutive_failures"], retry_s=wait)
                if st["consecutive_failures"] == FAILS_BEFORE_ALERT:
                    op.alerts.emit(Alert(op.clock(), SERVICE, CRITICAL,
                                         "El ciclo de operación falla",
                                         f"{FAILS_BEFORE_ALERT} fallos seguidos: "
                                         f"{st['last_error']}", SERVICE))
            st["next_cycle_at"] = op.clock() + int(wait * 1000)
            op.heartbeat()
            await self._sleep(wait)
        st["state"] = "detenido"
