"""Rutas del motor de riesgo (T29): decisión sobre el plan vigente, registro y kill-switch.

Sin órdenes: la cuenta es el libro SIMULADO con capital supuesto, y la decisión se muestra en
la UI con el tamaño aprobado o los motivos del veto.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Query

from eim.api.reports_db import ReportStore
from eim.api.trades import sync_trades
from eim.core import Mode
from eim.data.store import Store
from eim.data.timeframes import SYMBOLS, TF_MS
from eim.execution.sim_ledger import SimLedger
from eim.risk import KillSwitch, RiskEngine, global_kill_switch, load_config
from eim.risk.inputs import account_from_trades, market_context, plan_request
from eim.risk.journal import RiskJournal

MODE = Mode.SIMULADO
PAPER_EQUITY = 10_000.0          # capital simulado (supuesto, igual que el backtest de T25)
ACCOUNT_SOURCE = "libro SIMULADO (T15), capital supuesto 10 000 USDT"


def _now() -> int:
    return int(time.time() * 1000)


def _check(symbol: str, tf: str) -> None:
    if symbol not in SYMBOLS or tf not in TF_MS:
        raise HTTPException(400, f"símbolo o marco no soportado: {symbol} {tf}")


def build_risk_router(store: Store, reports: ReportStore,
                      clock: Callable[[], int] = _now,
                      kill: KillSwitch | None = None) -> APIRouter:
    con, lock = reports.connection
    ledger = SimLedger(con, lock)
    journal = RiskJournal(con, lock)
    cfg = load_config()
    kill = kill or global_kill_switch()
    engine = RiskEngine(cfg, journal, kill)
    router = APIRouter(prefix="/v2/risk")

    def config_view() -> dict:
        return cfg.model_dump(include={"version", "sha256", "risk_per_trade", "max_leverage",
                                       "max_daily_loss", "max_weekly_loss", "max_open_trades"})

    @router.get("")
    def risk(symbol: str = "ETHUSDT", tf: str = "1h") -> dict:
        """Evalúa el plan vigente del agente `plan` (y registra la decisión)."""
        _check(symbol, tf)
        now, bar = clock(), TF_MS[tf]
        base = {"mode": MODE.value, "config": config_view(), "kill_switch": kill.state()}
        latest = reports.latest(symbol, tf)
        rep = next((r for r in latest if r.agent_id == "plan"), None)
        req = plan_request(rep, symbol, tf, MODE) if rep is not None else None
        if req is None:
            return {**base, "plan": None, "decision": None,
                    "detail": "sin plan vigente: nada que dimensionar"}
        sync_trades(store, reports, ledger, symbol, tf)
        # la operación simulada de este mismo plan es la que se dimensiona: no cuenta
        trades = [t for s in SYMBOLS for t in ledger.trades(s, tf)
                  if not (t.symbol == symbol and t.plan_id == req.plan_id)]
        last = store.read_candles(symbol, tf, last=1)
        account = account_from_trades(trades, PAPER_EQUITY, cfg.risk_per_trade, now, bar,
                                      ACCOUNT_SOURCE)
        market = market_context(latest, last[-1].t + bar if last else None, now, bar)
        d = engine.evaluate(req, account, market)
        return {**base, "plan": req.model_dump(mode="json"),
                "decision": d.model_dump(mode="json", exclude={"seal"}),
                "account": account.model_dump()}

    @router.get("/decisions")
    def decisions(symbol: str = "ETHUSDT", tf: str = "1h",
                  limit: int = Query(200, ge=1, le=2000)) -> dict:
        _check(symbol, tf)
        rows = journal.query(symbol, tf, limit)
        return {"mode": MODE.value,
                "decisions": [d.model_dump(mode="json", exclude={"seal"}) for d in rows]}

    @router.get("/kill-switch")
    def kill_state() -> dict:
        return kill.state()

    @router.post("/kill-switch/activate")
    def kill_on(reason: str = Query("activado manualmente", max_length=200)) -> dict:
        kill.activate(reason, clock(), by="manual")
        return kill.state()

    @router.post("/kill-switch/deactivate")
    def kill_off(reason: str = Query("", max_length=200)) -> dict:
        kill.deactivate(clock(), by="manual", reason=reason)
        return kill.state()

    return router
