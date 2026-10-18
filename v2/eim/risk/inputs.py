"""Entradas del motor desde objetos del sistema (funciones puras, sin I/O).

- `plan_request`: reporte del agente `plan` (T13) → `PlanRequest` (None si no hay plan vigente).
- `account_from_trades`: estado de cuenta desde el libro SIMULADO (T15) con riesgo fijo.
- `market_context`: calidad de datos y ventanas de evento desde los últimos reportes.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

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


def _utc(t: int) -> str:
    return datetime.fromtimestamp(t / 1000, UTC).strftime("%m-%d %H:%M")


def calendar_at(r: AgentReport, now: int) -> tuple[bool, str, bool, str]:
    """(blackout, motivo, ventana sin blackout, motivo) del reporte de `calendar` a la hora `now`.

    Combina lo que el agente vio al cierre de vela (`blackout`, `window`) con sus
    `risk_windows` evaluadas contra la hora real de la decisión (T36-1/T44): una ventana que
    empezó después del cierre también cuenta, y una ya terminada no levanta lo que el agente vio.
    """
    m = r.metrics
    blackout, b_why = bool(m.get("blackout")), str(m.get("blackout_reason") or "")
    window, w_why = bool(m.get("window")), ""
    if window:
        ev = m.get("window_event") or {}
        w_why = (f"ventana {m['window']}-evento: {ev.get('name', '')} "
                 f"(impacto {ev.get('impact', '?')})")
    for w in m.get("risk_windows") or []:
        if not (w.get("start", 0) <= now < w.get("end", 0)):
            continue
        why = (f"ventana de evento {w.get('name', '')} ({w.get('impact', '?')}, "
               f"{_utc(w['start'])}–{_utc(w['end'])} UTC) activa a la hora de decidir")
        if w.get("blackout") and not blackout:
            blackout, b_why = True, why
        elif not w.get("blackout") and not window:
            window, w_why = True, why
    return blackout, b_why, window and not blackout, w_why


def market_context(reports: Iterable[AgentReport], last_close_t: int | None, now: int,
                   bar_ms: int, last_price: float | None = None) -> MarketContext:
    """`calendar` abre una ventana de evento con blackout (veto) o sin él (solo reduce el
    tamaño, T44), según lo que vio al cierre y sus `risk_windows` a la hora `now`.
    `context.metrics.event_pause` solo puede añadir una pausa (nunca levanta la del calendario)."""
    status: dict[str, str] = {}
    blackout = pause = window = False
    b_why = p_why = w_why = ""
    for r in reports:
        status[r.agent_id] = r.status
        if r.agent_id == "calendar" and r.status != "no_data":
            blackout, b_why, window, w_why = calendar_at(r, now)
        if r.agent_id == "context" and r.metrics.get("event_pause"):
            pause = True
            p_why = f"contexto: riesgo de evento {r.metrics.get('event_risk', 'alto')}"
    return MarketContext(now=now, bar_ms=bar_ms, last_close_t=last_close_t, last_price=last_price,
                         agent_status=status, blackout=blackout, blackout_reason=b_why,
                         event_window=window, event_reason=w_why,
                         event_pause=pause, pause_reason=p_why)
