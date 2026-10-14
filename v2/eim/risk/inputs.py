"""Entradas del motor desde objetos del sistema (funciones puras, sin I/O).

- `plan_request`: reporte del agente `plan` (T13) → `PlanRequest` (None si no hay plan vigente).
- `account_from_trades`: estado de cuenta desde el libro SIMULADO (T15) con riesgo fijo.
- `market_context`: calidad de datos y ventanas de evento desde los últimos reportes.
"""

from __future__ import annotations

from collections.abc import Iterable

from eim.core import AgentReport, Mode
from eim.execution.sim_ledger import Trade
from eim.risk.models import AccountState, MarketContext, PlanRequest

DAY_MS = 86_400_000
_MONDAY0 = 4 * DAY_MS     # 1970-01-01 fue jueves → el lunes 1970-01-05 empieza en 4 días


def plan_request(report: AgentReport, symbol: str, timeframe: str,
                 mode: Mode = Mode.SIMULADO) -> PlanRequest | None:
    plan = report.metrics.get("plan") if report.agent_id == "plan" else None
    if not plan or plan.get("status") != "VIGENTE" or not report.overlays:
        return None
    return PlanRequest(
        symbol=symbol, timeframe=timeframe, plan_id=report.overlays[0].id,
        side=1 if plan["side"] == "long" else -1, entry=float(plan["entry"]),
        sl=float(plan["sl"]), tp=tuple(float(x) for x in plan["tp"]),
        rr=plan.get("rr"), mode=mode, asof=report.asof)


def _day0(t: int) -> int:
    return t - t % DAY_MS


def _week0(t: int) -> int:
    return t - (t - _MONDAY0) % (7 * DAY_MS)


def account_from_trades(trades: Iterable[Trade], initial_equity: float, risk_frac: float,
                        now: int, bar_ms: int, source: str) -> AccountState:
    """Capital compuesto con riesgo fijo: cada operación cerrada aporta `r · risk_frac · E`.

    Solo cuenta lo conocido en `now` (cierre de la vela de salida ≤ now). Día y semana en UTC
    (la semana empieza el lunes).
    """
    closed = sorted((t for t in trades if t.r is not None and t.exit_t is not None
                     and t.exit_t + bar_ms <= now), key=lambda t: t.exit_t or 0)
    eq = peak = initial_equity
    day_eq = week_eq = None
    d0, w0 = _day0(now), _week0(now)
    streak, last_loss = 0, None
    for t in closed:
        done = (t.exit_t or 0) + bar_ms
        if day_eq is None and done >= d0:
            day_eq = eq
        if week_eq is None and done >= w0:
            week_eq = eq
        eq *= 1 + (t.r or 0.0) * risk_frac
        peak = max(peak, eq)
        if (t.r or 0.0) < 0:
            streak, last_loss = streak + 1, done
        else:
            streak = 0
    opened = tuple(t.symbol for t in trades
                   if t.entry_t + bar_ms <= now and (t.exit_t is None or t.exit_t + bar_ms > now))
    return AccountState(
        equity=eq, day_start_equity=eq if day_eq is None else day_eq,
        week_start_equity=eq if week_eq is None else week_eq, peak_equity=peak,
        open_symbols=opened, consecutive_losses=streak, last_loss_t=last_loss, source=source)


def market_context(reports: Iterable[AgentReport], last_close_t: int | None, now: int,
                   bar_ms: int, last_price: float | None = None) -> MarketContext:
    """`calendar.metrics.blackout` abre una ventana de evento; `context.metrics.event_pause`
    solo puede añadir una pausa (nunca levanta la del calendario)."""
    status: dict[str, str] = {}
    blackout = pause = False
    b_why = p_why = ""
    for r in reports:
        status[r.agent_id] = r.status
        if r.agent_id == "calendar" and r.metrics.get("blackout"):
            blackout, b_why = True, str(r.metrics.get("blackout_reason") or "")
        if r.agent_id == "context" and r.metrics.get("event_pause"):
            pause = True
            p_why = f"contexto: riesgo de evento {r.metrics.get('event_risk', 'alto')}"
    return MarketContext(now=now, bar_ms=bar_ms, last_close_t=last_close_t, last_price=last_price,
                         agent_status=status, blackout=blackout, blackout_reason=b_why,
                         event_pause=pause, pause_reason=p_why)
