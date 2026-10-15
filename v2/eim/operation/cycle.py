"""Un ciclo de operación: datos → agentes → síntesis → plan → riesgo → ejecución → control.

Orden por símbolo: sincroniza velas (marco operado y marco de camino), mueve el precio del
simulador por el camino de cada vela cerrada (SL/TP intravela), y al cerrar una vela del
marco operado corre los agentes (la síntesis va dentro del agente `plan`), el pronóstico y
la decisión de riesgo; si se aprueba, se envía por la puerta única (`RiskDesk.execute`).
Después: capital → reglas del kill-switch → reconciliación (cierra todo si está activo) →
alertas. Cada paso falla de forma aislada y queda en el resultado del ciclo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException

from eim.agents.registry import AgentRegistry
from eim.agents.runner import run_agents
from eim.api.reports_db import ReportStore
from eim.api.risk import RiskDesk
from eim.core import Candle
from eim.data.providers.base import Provider
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from eim.data.sync import sync_candles
from eim.data.timeframes import FOCUS, tf_ms
from eim.execution.broker import BrokerError
from eim.execution.sim_broker import SimBroker
from eim.operation.alerts import AlertCenter, conditions
from eim.operation.equity import EquityBook, drawdown
from eim.operation.notify import JsonLog
from eim.operation.state import Cursors

DAY_MS = 86_400_000


@dataclass(frozen=True)
class OperationParams:
    symbols: tuple[str, ...] = FOCUS      # foco actual: solo BTCUSDT
    timeframe: str = "1h"                 # marco operado (el del backtest de T25/T27)
    path_tf: str = "15m"                  # marco que mueve el precio del simulador
    poll_s: float = 60.0
    history_bars: int = 1000              # historia mínima que se mantiene sincronizada
    snapshot_bars: int = 500
    agent_timeout_s: float = 30.0
    max_catchup_ms: int = 7 * DAY_MS      # tras una caída larga no se reproduce más que esto
    disconnect_alert_ms: int = 120_000
    drawdown_warn: float = 0.05           # aviso; el kill-switch actúa en risk_v1 (15 %)


@dataclass
class CycleResult:
    t: int
    ok: bool = True
    analyzed: list[str] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    equity: float | None = None
    drawdown: float | None = None
    recon_ok: bool | None = None

    def to_json(self) -> dict:
        return dict(self.__dict__)


def walk(broker: SimBroker, symbol: str, c: Candle) -> None:
    """Mueve el precio del simulador por el camino de la vela: apertura (salto, respeta
    huecos), extremo adverso a la posición, extremo favorable, cierre. Entre puntos se pasa
    por cada disparo pendiente, así SL/TP se llenan en su precio (sin deslizamiento: supuesto)."""
    pos = broker.position(symbol).qty
    broker.set_price(symbol, c.o)
    cur = c.o
    for p in ([c.h, c.l] if pos < 0 else [c.l, c.h]) + [c.c]:
        lo, hi = min(cur, p), max(cur, p)
        trig = sorted({o.trigger for o in broker.open_orders(symbol)
                       if o.conditional and o.trigger is not None and lo < o.trigger < hi},
                      reverse=p < cur)
        for x in trig:
            broker.set_price(symbol, x)
        broker.set_price(symbol, p)
        cur = p


class OperationCycle:
    def __init__(self, store: Store, provider: Provider, reports: ReportStore,
                 registry: AgentRegistry, desk: RiskDesk, book: EquityBook | None,
                 alerts: AlertCenter, log: JsonLog, params: OperationParams,
                 cursors: Cursors, forecaster=None) -> None:
        self.store, self.provider, self.reports, self.registry = store, provider, reports, registry
        self.desk, self.book, self.alerts, self.log = desk, book, alerts, log
        self.p, self.cur, self.forecaster = params, cursors, forecaster
        self.data_fail_since: dict[str, int] = {}
        self.agent_status: dict[str, dict[str, str]] = {}

    @property
    def rt(self):
        return self.desk.rt

    # --- pasos -------------------------------------------------------------
    def _sync(self, sym: str, now: int) -> bool:
        tf, ptf = self.p.timeframe, self.p.path_tf
        try:
            sync_candles(self.store, self.provider, sym, tf,
                         now - self.p.history_bars * tf_ms(tf), now)
            sync_candles(self.store, self.provider, sym, ptf, now - 2 * DAY_MS, now)
        except Exception as e:  # noqa: BLE001 - red caída, límite de tasa…
            self.data_fail_since.setdefault(sym, now)
            self.log.write("datos_fallidos", "warn", symbol=sym, error=f"{type(e).__name__}: {e}")
            return False
        self.data_fail_since.pop(sym, None)
        return True

    def _feed(self, sym: str, now: int) -> None:
        broker = self.rt.svc.broker
        ptf = self.p.path_tf
        fed = self.cur.fed.get(sym)
        if fed is None:
            last = self.store.read_candles(sym, ptf, last=1)
            if last:
                with self.rt.lock:
                    broker.set_price(sym, last[-1].c)
                self.cur.fed[sym] = last[-1].t
            return
        start = max(fed + tf_ms(ptf), now - self.p.max_catchup_ms)
        with self.rt.lock:
            for c in self.store.read_candles(sym, ptf, start):
                walk(broker, sym, c)
                self.cur.fed[sym] = c.t

    def _analyze(self, sym: str) -> bool:
        tf = self.p.timeframe
        last = self.store.read_candles(sym, tf, last=1)
        if not last or last[-1].t <= self.cur.analyzed.get(sym, -1):
            return False
        asof = last[-1].t + tf_ms(tf)
        done = {r.asof for r in self.reports.latest(sym, tf)}
        if asof not in done:        # la API pudo analizarla ya (canal abierto en la UI)
            snap = build_snapshot(self.store, sym, tf, self.p.snapshot_bars, asof=asof)
            reps = run_agents(self.registry.latest(), snap, timeout=self.p.agent_timeout_s)
            self.reports.save(sym, tf, reps)
            if self.forecaster is not None:
                try:
                    self.forecaster.run(sym, tf)
                except Exception as e:  # noqa: BLE001 - el pronóstico no frena la operación
                    self.log.write("pronostico_fallido", "warn", symbol=sym, error=str(e))
        self.agent_status[sym] = {r.agent_id: r.status for r in self.reports.latest(sym, tf)}
        self.cur.analyzed[sym] = last[-1].t
        return True

    def _decide(self, sym: str, res: CycleResult) -> None:
        tf = self.p.timeframe
        try:
            view = (self.desk.execute(sym, tf) if self.rt.svc is not None
                    else self.desk.evaluate(sym, tf)[0])
        except HTTPException as e:
            res.errors.append(f"{sym}: decisión/envío: {e.detail}")
            self.log.write("envio_fallido", "error", symbol=sym, error=str(e.detail))
            return
        d = view.get("decision")
        row = {"symbol": sym, "plan": (view.get("plan") or {}).get("plan_id"),
               "approved": d["approved"] if d else None,
               "reasons": list(d["reasons"]) if d else [view.get("detail", "")],
               "executed": bool(view.get("executed")),
               "trade": (view.get("trade") or {}).get("key")}
        res.decisions.append(row)
        self.log.write("decision", **row)

    # --- ciclo completo ----------------------------------------------------
    def run(self, now: int) -> CycleResult:
        res = CycleResult(t=now)
        rt, kill, cfg = self.rt, self.desk.kill, self.desk.cfg
        if self.cur.started_at is None:
            self.cur.started_at = now
        for sym in self.p.symbols:
            ok = self._sync(sym, now)
            if not ok:
                res.errors.append(f"{sym}: sin datos del proveedor")
            if rt.paper:
                self._feed(sym, now)
            if ok and self._analyze(sym):
                res.analyzed.append(sym)
                self._decide(sym, res)
        if rt.svc is not None:
            try:
                res.equity = rt.equity(fresh=True)
                peak = max(self.book.peak() or res.equity, res.equity) if self.book else None
                res.drawdown = drawdown(res.equity, peak)
                if self.book is not None:
                    self.book.record(now, res.equity)
                kill.check_rules(cfg, now, drawdown=res.drawdown)
            except BrokerError as e:
                res.errors.append(f"capital no disponible: {e}")
            try:
                rep = rt.reconcile(now)
                res.recon_ok = rep.ok
            except BrokerError as e:
                res.errors.append(f"reconciliación fallida: {e}")
                res.recon_ok = False
        recon = rt.recon.last.to_json() if rt.recon and rt.recon.last else None
        self.alerts.update(now, conditions(
            now=now, data_fail_since={s: self.data_fail_since.get(s) for s in self.p.symbols},
            disconnect_ms=self.p.disconnect_alert_ms, recon=recon, kill=kill.state(),
            drawdown=res.drawdown or 0.0, drawdown_warn=self.p.drawdown_warn,
            drawdown_kill=cfg.kill_max_drawdown, agent_status=self.agent_status,
            critical=cfg.critical_agents))
        res.ok = not res.errors
        return res
