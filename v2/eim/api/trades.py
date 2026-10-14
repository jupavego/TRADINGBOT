"""Rutas de operaciones simuladas, bitácora y reproducción (T15). Sin llamadas a exchanges."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from eim.api.live import overlays_of, synthesis_of
from eim.api.reports_db import ReportStore
from eim.core import Mode
from eim.data.store import Store
from eim.data.timeframes import SYMBOLS, TF_MS
from eim.execution.sim_ledger import SimLedger, Trade, build_trades, trade_at

MODE = Mode.SIMULADO.value


def _check(symbol: str, tf: str) -> None:
    if symbol not in SYMBOLS or tf not in TF_MS:
        raise HTTPException(400, f"símbolo o marco no soportado: {symbol} {tf}")


def sync_trades(store: Store, reports: ReportStore, ledger: SimLedger, symbol: str,
                tf: str) -> list[Trade]:
    """Reconstruye el libro desde los planes persistidos y lo guarda."""
    plans = reports.query(symbol, tf, agent_id="plan", limit=100_000)
    t0 = min((o.t_from for r in plans for o in r.overlays), default=None)
    candles = store.read_candles(symbol, tf, start=t0) if t0 is not None else []
    trades = build_trades(symbol, tf, plans, candles)
    ledger.replace(symbol, tf, trades)
    return trades


def build_trades_router(store: Store, reports: ReportStore) -> APIRouter:
    con, lock = reports.connection
    ledger = SimLedger(con, lock)
    router = APIRouter(prefix="/v2")

    def sync(symbol: str, tf: str) -> list[Trade]:
        return sync_trades(store, reports, ledger, symbol, tf)

    @router.get("/trades")
    def trades(symbol: str = "ETHUSDT", tf: str = "1h") -> dict:
        _check(symbol, tf)
        ts = sync(symbol, tf)
        return {"mode": MODE, "trades": [t.to_json() for t in ts]}

    @router.get("/journal")
    def journal(symbol: str = "ETHUSDT", tf: str = "1h",
                limit: int = Query(200, ge=1, le=2000)) -> dict:
        """Decisiones del agente de plan y operaciones simuladas, con su evidencia."""
        _check(symbol, tf)
        ts = sync(symbol, tf)
        decisions = []
        for r in reports.query(symbol, tf, agent_id="plan", limit=limit):
            plan = r.metrics.get("plan") or {}
            decisions.append({
                "asof": r.asof, "plan_id": r.overlays[0].id if r.overlays else None,
                "action": (f"{plan.get('side')} · {plan.get('status')}" if plan
                           else "sin plan"),
                "bias": r.bias, "confidence": r.confidence, "evidence": r.evidence,
                "plan": plan or None, "mode": plan.get("mode", Mode.ANALISIS.value),
            })
        return {"mode": MODE, "decisions": decisions,
                "trades": [t.to_json() for t in reversed(ts)][:limit]}

    @router.get("/replay/asofs")
    def replay_asofs(symbol: str = "ETHUSDT", tf: str = "1h",
                     limit: int = Query(2000, ge=1, le=20000)) -> list[int]:
        _check(symbol, tf)
        return reports.asofs(symbol, tf, limit)

    @router.get("/replay")
    def replay(asof: int, symbol: str = "ETHUSDT", tf: str = "1h",
               n: int = Query(500, ge=1, le=5000)) -> dict:
        """Estado tal como estaba en `asof`: velas, reportes, capas y operaciones."""
        _check(symbol, tf)
        rs = reports.at(symbol, tf, asof)
        view = [v for t in sync(symbol, tf) if (v := trade_at(t, asof))]
        candles = store.read_candles(symbol, tf, end=asof, last=n)
        return {
            "asof": asof, "mode": MODE, "candles": [c.model_dump() for c in candles],
            "reports": [r.model_dump() for r in rs], "overlays": overlays_of(rs),
            "synthesis": synthesis_of(rs),
            "trades": [t.to_json() for t in view],
        }

    return router
