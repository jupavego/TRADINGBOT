"""Panel «Operación» (T31): estado del servicio, posiciones, P&L, riesgo usado, vetos, alertas.

El kill-switch se maneja con las rutas de `/v2/risk/kill-switch` (mismo estado global). Sin
servicio de operación (`EIM_OPERATE` apagado) la ruta responde igual, con `service: null`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query

from eim.api.execution import confirm
from eim.api.risk import RiskDesk
from eim.execution.broker import BrokerError
from eim.execution.sim_broker import SimBroker
from eim.operation import weekly
from eim.operation.equity import drawdown


def _positions(desk: RiskDesk) -> list[dict]:
    svc = desk.rt.svc
    if svc is None:
        return []
    out = []
    for t in svc.active():
        last = svc.broker.price(t.symbol) if isinstance(svc.broker, SimBroker) else None
        if last is None:
            c = desk.store.read_candles(t.symbol, "15m", last=1)
            last = c[-1].c if c else None
        upnl = (None if last is None or t.avg_entry is None
                else (last - t.avg_entry) * t.side * t.filled)
        out.append({**{k: getattr(t, k) for k in ("key", "symbol", "side", "qty", "filled",
                                                 "avg_entry", "sl", "tp", "status",
                                                 "opened_at", "leverage")},
                    "last": last, "upnl": upnl,
                    "risk": abs((t.avg_entry or 0) - t.sl) * t.filled if t.avg_entry else None})
    return out


def _pnl_and_risk(desk: RiskDesk, positions: list[dict], now: int) -> tuple[dict, dict]:
    rt, cfg = desk.rt, desk.cfg
    if rt.svc is None:
        return {}, {}
    acc = rt.account(now)
    eq = acc.equity
    closed = [t for t in rt.svc.trades.values() if t.pnl is not None]
    first = rt.equity_book.series()[:1] if rt.equity_book else []
    start = first[0][1] if first else eq
    pnl = {"equity": eq, "start_equity": start, "total_return": eq / start - 1 if start else None,
           "day_change": eq - acc.day_start_equity, "week_change": eq - acc.week_start_equity,
           "realized_gross": sum(t.pnl or 0.0 for t in closed), "n_closed": len(closed),
           "unrealized": sum(p["upnl"] or 0.0 for p in positions),
           "drawdown": drawdown(eq, acc.peak_equity), "peak_equity": acc.peak_equity,
           "source": acc.source}
    open_risk = sum(p["risk"] or 0.0 for p in positions)

    def used(x: float, limit: float) -> dict:
        return {"value": x, "limit": limit, "frac": x / limit if limit else None}

    day_loss = max(0.0, acc.day_start_equity - eq) / acc.day_start_equity
    week_loss = max(0.0, acc.week_start_equity - eq) / acc.week_start_equity
    risk = {"open_risk": used(open_risk / eq if eq else 0.0,
                              cfg.risk_per_trade * cfg.max_open_trades),
            "daily_loss": used(day_loss, cfg.max_daily_loss),
            "weekly_loss": used(week_loss, cfg.max_weekly_loss),
            "drawdown": used(pnl["drawdown"], cfg.kill_max_drawdown),
            "open_trades": used(len(positions), cfg.max_open_trades),
            "consecutive_losses": used(acc.consecutive_losses, cfg.max_consecutive_losses)}
    return pnl, risk


def build_operation_router(desk: RiskDesk, op_ref: Callable[[], object | None],
                           reports_dir: Path,
                           clock: Callable[[], int] = lambda: int(time.time() * 1000)
                           ) -> APIRouter:
    """`op_ref()` devuelve la `Operation` en marcha (o None): se crea en el arranque."""
    router = APIRouter(prefix="/v2/operation")

    @router.get("")
    def overview(vetoes: int = Query(15, ge=1, le=200), alerts: int = Query(30, ge=1, le=500)
                 ) -> dict:
        now, op, rt = clock(), op_ref(), desk.rt
        positions = _positions(desk)
        try:
            pnl, risk = _pnl_and_risk(desk, positions, now)
        except BrokerError as e:
            pnl, risk = {"error": f"cuenta no disponible: {e}"}, {}
        vet = desk.journal.recent(now - weekly.WEEK_MS, approved=False, limit=vetoes)
        return {
            "now": now, "mode": desk.mode.value, "execution_enabled": rt.svc is not None,
            "execution_error": rt.error,
            "service": dict(op.status) if op is not None else None,
            "positions": positions, "pnl": pnl, "risk": risk,
            "vetoed": [{"t": d.decided_at, "symbol": d.symbol, "timeframe": d.timeframe,
                        "plan_id": d.plan_id, "side": d.side, "reasons": list(d.reasons)}
                       for d in vet],
            "alerts": [a.to_json() for a in op.alerts.recent(limit=alerts)] if op else [],
            "active_alerts": op.alerts.active if op else [],
            "alert_sink_errors": op.alerts.sink_errors if op else [],
            "kill_switch": desk.kill.state(),
            "reconciliation": rt.recon.last.to_json() if rt.recon and rt.recon.last else None,
            "reports": sorted(p.name for p in reports_dir.glob("*.md"))[-12:]
            if reports_dir.exists() else [],
        }

    @router.post("/report")
    def make_report(start: int | None = None, end: int | None = None,
                    x_eim_confirm: str | None = Header(None)) -> dict:
        """Informe a demanda: por defecto, la semana en curso hasta ahora."""
        confirm(x_eim_confirm, "report")
        op = op_ref()
        if op is None:
            raise HTTPException(409, "servicio de operación apagado (EIM_OPERATE=1)")
        now = clock()
        t0 = start if start is not None else weekly.week_bounds(now)[0]
        t1 = end if end is not None else now
        if t1 <= t0:
            raise HTTPException(400, "periodo vacío")
        name = f"parcial_{weekly.week_label(t0)}" if start is None else None
        out = op.write_report(t0, t1, name or f"periodo_{t0}_{t1}")
        return {"json": out["json"], "md": out["md"]}

    @router.get("/report")
    def read_report(name: str = Query(..., pattern=r"^[\w.-]+\.md$")) -> dict:
        p = reports_dir / name
        if not p.exists():
            raise HTTPException(404, f"no existe {name}")
        return {"name": name, "markdown": p.read_text(encoding="utf-8")}

    return router
