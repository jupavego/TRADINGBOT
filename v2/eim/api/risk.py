"""Rutas del motor de riesgo (T29): decisión sobre el plan vigente, registro y kill-switch.

Sin broker (por defecto) no hay órdenes: la cuenta es el libro SIMULADO con capital supuesto y
la decisión se muestra en la UI con el tamaño aprobado o los motivos del veto. Con ejecución en
testnet (T30, `eim/api/execution.py`) el modo pasa a TESTNET, la cuenta sale del exchange y
`POST /v2/risk/execute` envía el plan aprobado por la única puerta (`OrderGateway`).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import APIRouter, Header, HTTPException, Query

from eim.api.execution import ExecutionRuntime, confirm
from eim.api.reports_db import ReportStore
from eim.api.trades import sync_trades
from eim.data.store import Store
from eim.data.timeframes import SYMBOLS, TF_MS
from eim.execution.broker import BrokerError
from eim.execution.gateway import OrderGateway
from eim.execution.sim_ledger import SimLedger
from eim.risk import KillSwitch, RiskDecision, RiskEngine, global_kill_switch, load_config
from eim.risk.inputs import account_from_trades, market_context, plan_request
from eim.risk.journal import RiskJournal

PAPER_EQUITY = 10_000.0          # capital simulado (supuesto, igual que el backtest de T25)
ACCOUNT_SOURCE = "libro SIMULADO (T15), capital supuesto 10 000 USDT"


def _now() -> int:
    return int(time.time() * 1000)


def _confirm(value: str | None, expected: str = "kill-switch") -> None:
    confirm(value, expected)


def _check(symbol: str, tf: str) -> None:
    if symbol not in SYMBOLS or tf not in TF_MS:
        raise HTTPException(400, f"símbolo o marco no soportado: {symbol} {tf}")


class RiskDesk:
    """Evaluación del plan vigente y envío por la puerta única. La usan la API y el servicio
    de operación continua (T31): una sola ruta de código hacia las órdenes."""

    def __init__(self, store: Store, reports: ReportStore, clock: Callable[[], int] = _now,
                 kill: KillSwitch | None = None, runtime: ExecutionRuntime | None = None) -> None:
        con, lock = reports.connection
        self.store, self.reports, self.clock = store, reports, clock
        self.ledger = SimLedger(con, lock)
        self.journal = RiskJournal(con, lock)
        self.cfg = load_config()
        self.kill = kill or global_kill_switch()
        self.engine = RiskEngine(self.cfg, self.journal, self.kill)
        self.rt = runtime or ExecutionRuntime()
        self.mode = self.rt.mode

    def config_view(self) -> dict:
        return self.cfg.model_dump(include={"version", "sha256", "risk_per_trade",
                                            "max_leverage", "max_daily_loss",
                                            "max_weekly_loss", "max_open_trades"})

    def evaluate(self, symbol: str, tf: str) -> tuple[dict, RiskDecision | None]:
        """Evalúa el plan vigente del agente `plan` (y registra la decisión)."""
        _check(symbol, tf)
        rt, store, reports = self.rt, self.store, self.reports
        now, bar = self.clock(), TF_MS[tf]
        base = {"mode": self.mode.value, "config": self.config_view(),
                "kill_switch": self.kill.state()}
        latest = reports.latest(symbol, tf)
        rep = next((r for r in latest if r.agent_id == "plan"), None)
        req = plan_request(rep, symbol, tf, self.mode) if rep is not None else None
        if req is None:
            return {**base, "plan": None, "decision": None,
                    "detail": "sin plan vigente: nada que dimensionar"}, None
        if rt.svc is not None:
            try:
                account = rt.account(now)
            except BrokerError as e:
                raise HTTPException(
                    502, f"cuenta de {self.mode.value} no disponible: {e}") from None
        else:
            sync_trades(store, reports, self.ledger, symbol, tf)
            # la operación simulada de este mismo plan es la que se dimensiona: no cuenta
            trades = [t for s in SYMBOLS for t in self.ledger.trades(s, tf)
                      if not (t.symbol == symbol and t.plan_id == req.plan_id)]
            account = account_from_trades(trades, PAPER_EQUITY, self.cfg.risk_per_trade, now,
                                          bar, ACCOUNT_SOURCE)
        last = store.read_candles(symbol, tf, last=1)
        market = market_context(latest, last[-1].t + bar if last else None, now, bar,
                                last[-1].c if last else None)
        why = (rep.evidence or ["plan vigente del agente plan"])[0]
        prop = req.as_proposal("agents.plan", rep.version, confidence=rep.confidence,
                               reason=why, horizon_ms=rep.horizon_bars * bar or None,
                               max_age_ms=self.cfg.max_plan_age_bars * bar, exit_mode="bracket")
        d = self.engine.evaluate(req, account, market, proposal=prop)
        return {**base, "plan": req.model_dump(mode="json"),
                "decision": d.model_dump(mode="json", exclude={"seal"}),
                "account": account.model_dump()}, d

    def execute(self, symbol: str, tf: str) -> dict:
        """Evalúa y, si el motor aprueba, envía por `OrderGateway`. Lanza HTTPException."""
        rt = self.rt
        if rt.svc is None:
            raise HTTPException(409, rt.error or "ejecución desactivada (EIM_EXECUTION)")
        view, d = self.evaluate(symbol, tf)
        if d is None or not d.approved:
            return {**view, "executed": False}
        try:
            with rt.lock:
                key = OrderGateway(self.engine, rt.svc).submit(d, self.clock())
        except PermissionError as e:
            raise HTTPException(409, str(e)) from None
        except BrokerError as e:
            raise HTTPException(502, str(e)) from None
        return {**view, "executed": True, "trade": rt.svc.trades[key].to_json()}


def build_risk_router(store: Store, reports: ReportStore,
                      clock: Callable[[], int] = _now,
                      kill: KillSwitch | None = None,
                      runtime: ExecutionRuntime | None = None,
                      desk: RiskDesk | None = None) -> APIRouter:
    desk = desk or RiskDesk(store, reports, clock, kill, runtime)
    kill, journal = desk.kill, desk.journal
    router = APIRouter(prefix="/v2/risk")

    @router.get("")
    def risk(symbol: str = "ETHUSDT", tf: str = "1h") -> dict:
        return desk.evaluate(symbol, tf)[0]

    @router.post("/execute")
    def execute(symbol: str = "ETHUSDT", tf: str = "1h",
                x_eim_confirm: str | None = Header(None)) -> dict:
        """Evalúa el plan vigente y, si el motor lo aprueba, lo envía al broker."""
        _confirm(x_eim_confirm, "execute")
        return desk.execute(symbol, tf)

    @router.get("/decisions")
    def decisions(symbol: str = "ETHUSDT", tf: str = "1h",
                  limit: int = Query(200, ge=1, le=2000)) -> dict:
        _check(symbol, tf)
        rows = journal.query(symbol, tf, limit)
        return {"mode": desk.mode.value,
                "decisions": [d.model_dump(mode="json", exclude={"seal"}) for d in rows]}

    @router.get("/kill-switch")
    def kill_state() -> dict:
        return kill.state()

    @router.post("/kill-switch/activate")
    def kill_on(reason: str = Query("activado manualmente", max_length=200),
                x_eim_confirm: str | None = Header(None)) -> dict:
        _confirm(x_eim_confirm)
        kill.activate(reason, desk.clock(), by="manual")
        return kill.state()

    @router.post("/kill-switch/deactivate")
    def kill_off(reason: str = Query("", max_length=200),
                 x_eim_confirm: str | None = Header(None)) -> dict:
        _confirm(x_eim_confirm)
        kill.deactivate(desk.clock(), by="manual", reason=reason)
        return kill.state()

    return router
