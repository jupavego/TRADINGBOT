"""Servicio supervisado: bucle de ciclos con latido, reintento con espera creciente y registro.

Dos niveles de reinicio automático:
1. Dentro del proceso (`Supervisor.run`): un ciclo que lanza una excepción no mata el bucle;
   se registra, se avisa (alerta «servicio» tras fallos seguidos) y se reintenta con espera
   exponencial (tope `max_backoff_s`). Tampoco lo matan el latido ni el aviso de un fallo.
2. Fuera del proceso (`eim.operation.watchdog`): relanza la API si muere o si el latido
   (`data/operation/heartbeat.json`) deja de avanzar.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from eim.api.forecast import DEFAULT_HORIZON
from eim.api.forecast_db import ForecastStore
from eim.api.risk import RiskDesk
from eim.data import backup
from eim.data.collectors import hft_ops
from eim.data.collectors.compact import compact_closed
from eim.execution.sim_broker import SimBroker
from eim.observability import hooks_service
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
from eim.operation.watchdog import write_heartbeat

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
                 extra_dbs: dict | None = None, backup_in_thread: bool = False,
                 clock: Callable[[], int] = _now) -> None:
        con, lock = reports.connection
        rt = desk.rt
        self.mode = desk.mode.value
        self.desk, self.store, self.params, self.clock = desk, store, params, clock
        self.reports_dir, self.edge_path = reports_dir, edge_path
        self.root = data_dir / "operation"
        self.data_dir, self.backup_dir, self.backup_keep = data_dir, backup_dir, backup_keep
        self._db = (con, lock)
        self.extra_dbs = extra_dbs or {}   # otras bases abiertas que entran en la copia (T73)
        self._step_lock = threading.RLock()
        self._compact_at = 0
        self._backup_retry_at = 0          # tras un fallo, reintento espaciado (BACKUP_RETRY_MS)
        self.backup_in_thread = backup_in_thread
        self._backup_lock = threading.Lock()                 # una copia a la vez
        self._backup_thread: threading.Thread | None = None
        self._backup_done: tuple[str, str] | None = None     # resultado del hilo, sin publicar
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
            self._obs_alerts(now)
            state.save(self.state_path, self.desk.rt.svc, self.cursors, self.mode)
            self.weekly_if_due(now)
            self.backup_if_due(now)
            self.compact_micro_if_due(now)
        row = res.to_json()
        row["cycle_t"] = row.pop("t")
        self.log.write("ciclo", "info" if res.ok else "warn", **row)
        return res

    def _obs_alerts(self, now: int) -> None:
        """Salud mínima del observatorio (T75): por transición, vía `op_alerts` + aviso local."""
        db = self.extra_dbs.get("obs.duckdb")
        if db is None:
            return
        try:
            from eim.observability.obs_alerts import obs_conditions
            self.alerts.update(now, obs_conditions(db[0], db[1], now))
        except Exception as e:  # noqa: BLE001 - el observatorio nunca tumba la operación
            self.log.write("obs_alertas_error", "warn", error=f"{type(e).__name__}: {e}")

    def heartbeat(self) -> None:
        """Latido del vigilante; si no se puede escribir tras reintentar, se avisa y se sigue."""
        self.status["last_heartbeat"] = self.clock()
        hooks_service.beat("operation.supervisor", mode=self.desk.mode,
                           status="ok" if not self.status["consecutive_failures"] else "degraded",
                           detail={"state": self.status["state"], "cycles": self.status["cycles"],
                                   "failures": self.status["consecutive_failures"]})
        if err := write_heartbeat(self.root / "heartbeat.json", {k: self.status[k] for k in (
                "last_heartbeat", "pid", "state", "mode", "cycles", "consecutive_failures")}):
            self.log.write("latido_fallido", "warn", error=f"{type(err).__name__}: {err}")

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
            started_at=self.cursors.started_at, hft_qc=self.hft_qc(t0, t1))

    def hft_qc(self, t0: int, t1: int) -> dict[str, dict]:
        """Resumen del control de calidad de la captura HFT (T78) por símbolo, si la hay."""
        out = {}
        for s in self.params.symbols:
            try:
                if (q := hft_ops.week_summary(self.data_dir, s, t0, t1)) is not None:
                    out[s] = q
            except Exception as e:  # noqa: BLE001 - un QC ilegible no impide el informe
                out[s] = {"error": f"{type(e).__name__}: {e}"}
        return out

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
        hooks_service.service_event("operation.report", "informe semanal escrito")

    def compact_micro_if_due(self, now: int) -> None:
        """Une cada hora los archivos de microestructura de las horas ya cerradas (acota el
        coste de leer ventanas largas). Cada pasada limita el trabajo; nunca frena la operación."""
        if now < self._compact_at:
            return
        self._compact_at = now + 3_600_000
        try:
            done = compact_closed(self.data_dir, now, max_dirs=12)
            if done:
                self.log.write("micro_compactada", horas=len(done),
                               archivos=sum(x[1] for x in done))
        except Exception as e:  # noqa: BLE001 - mantenimiento: se avisa en el registro y se sigue
            self.log.write("micro_compactada", "warn", error=f"{type(e).__name__}: {e}")

    def backup_if_due(self, now: int) -> None:
        """Copia de seguridad diaria (UTC). Un fallo alerta (una vez) y se reintenta cada
        `BACKUP_RETRY_MS` (no en cada ciclo); una copia con bases ausentes alerta y no se repite
        ese día. Nunca detiene la operación: con `backup_in_thread` (en vivo) corre en un hilo y
        el ciclo solo espera el tramo de `reports.duckdb` + estado (T115); el resultado se
        publica en el ciclo siguiente (las alertas no se tocan desde otro hilo)."""
        running = self._backup_thread is not None and self._backup_thread.is_alive()
        if not running and self._backup_done is not None:     # el hilo ya terminó de escribir
            done, self._backup_done = self._backup_done, None
            self._publish_backup(now, *done)
        if (self.backup_dir is None or now < self._backup_retry_at or running
                or not backup.due_today(self.backup_dir, now / 1000)):
            return
        if self.backup_in_thread:
            def run() -> None:
                self._backup_done = self._daily_backup(now)
            self._backup_thread = threading.Thread(target=run, name="eim-backup", daemon=True)
            self._backup_thread.start()
        else:
            self._publish_backup(now, *self._daily_backup(now))

    def _daily_backup(self, now: int) -> tuple[str, str]:
        """(título, detalle) de la alerta `copia_seguridad`; detalle vacío = copia completa."""
        try:
            s = backup.summary(self.backup_now(clock=lambda: now / 1000))
        except Exception as e:  # noqa: BLE001 - se alerta y se sigue operando
            err = f"{type(e).__name__}: {e}"
            self._backup_retry_at = now + BACKUP_RETRY_MS
            self.log.write("copia_seguridad", "warn", error=err)
            hooks_service.service_error("operation.backup", e)
            return "Copia de seguridad fallida", err
        self.log.write("copia_seguridad", "warn" if s["absent"] else "info", path=s["path"],
                       mb=round(s["bytes"] / 1e6, 1), seconds=s["seconds"], held_s=s["held_s"],
                       absent=s["absent"])
        hooks_service.service_event("operation.backup", "copia diaria hecha")
        if not s["absent"]:
            return "Copia de seguridad", ""             # resuelve un fallo o una incompleta
        return "Copia de seguridad incompleta", "; ".join(
            f"{k}: {v}" for k, v in s["absent"].items())

    def _publish_backup(self, now: int, title: str, err: str) -> None:
        self.alerts.update(now, [Condition("copia_seguridad", BACKUP, bool(err), WARN, title,
                                           err)])

    def backup_now(self, with_market: bool = False, clock: Callable[[], float] = time.time):
        """Copia a demanda o diaria, una a la vez. `reports.duckdb` y el estado del servicio se
        copian entre ciclos (coherentes entre sí); líderes, paper y observatorio, sin frenarlo."""
        if self.backup_dir is None:
            raise RuntimeError("sin carpeta de copias")
        with self._backup_lock:
            return backup.create(self.data_dir, self.backup_dir, con=self._db[0],
                                 lock=self._db[1], hold=self._step_lock,
                                 with_market=with_market, keep=self.backup_keep,
                                 extra_dbs=self.extra_dbs, clock=clock)


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
                hooks_service.service_error("operation.supervisor", e, mode=op.desk.mode)
                try:    # avisar del fallo tampoco puede matar el bucle
                    op.log.write("ciclo_fallido", "error", error=st["last_error"],
                                 consecutive=st["consecutive_failures"], retry_s=wait)
                    if st["consecutive_failures"] == FAILS_BEFORE_ALERT:
                        op.alerts.emit(Alert(op.clock(), SERVICE, CRITICAL,
                                             "El ciclo de operación falla",
                                             f"{FAILS_BEFORE_ALERT} fallos seguidos: "
                                             f"{st['last_error']}", SERVICE))
                except Exception as err:  # noqa: BLE001 - el bucle no debe morir
                    hooks_service.service_error("operation.supervisor", err, mode=op.desk.mode)
            try:    # ni el latido (2026-10-24: WinError 5 lo detuvo 9 min sin rastro)
                st["next_cycle_at"] = op.clock() + int(wait * 1000)
                op.heartbeat()
            except Exception as e:  # noqa: BLE001 - el bucle no debe morir
                hooks_service.service_error("operation.supervisor", e, mode=op.desk.mode)
            await self._sleep(wait)
        st["state"] = "detenido"
