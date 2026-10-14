"""Reglas de veto (funciones puras). Cada una devuelve un `Check`; aprobar exige todas ok."""

from __future__ import annotations

import math

from eim.risk.config import RiskConfig
from eim.risk.models import AccountState, Check, MarketContext, PlanRequest


def _c(rule: str, ok: bool, detail: str) -> Check:
    return Check(rule=rule, ok=ok, detail=detail)


def check_mode(p: PlanRequest, cfg: RiskConfig) -> Check:
    ok = p.mode.value in cfg.allowed_modes
    return _c("modo", ok, f"modo {p.mode.value}" + ("" if ok else " no permitido"))


def check_plan(p: PlanRequest, cfg: RiskConfig) -> Check:
    """Geometría coherente: lado definido, SL del lado de la pérdida, distancia razonable."""
    vals = [p.entry, p.sl, *p.tp]
    if p.side not in (1, -1):
        return _c("plan", False, "plan sin lado (side=0)")
    if not all(math.isfinite(v) and v > 0 for v in vals):
        return _c("plan", False, "precios no finitos o ≤ 0")
    if (p.entry - p.sl) * p.side <= 0:
        return _c("plan", False, "SL del lado equivocado de la entrada")
    if any((t - p.entry) * p.side <= 0 for t in p.tp):
        return _c("plan", False, "TP del lado equivocado de la entrada")
    frac = abs(p.entry - p.sl) / p.entry
    if frac < cfg.min_sl_frac:
        return _c("plan", False, f"SL a {frac:.3%} < {cfg.min_sl_frac:.3%} (dentro del ruido)")
    if frac > cfg.max_sl_frac:
        return _c("plan", False, f"SL a {frac:.2%} > {cfg.max_sl_frac:.2%}")
    rr = p.rr if p.rr is not None else (
        abs(p.tp[0] - p.entry) / abs(p.entry - p.sl) if p.tp else 0.0)
    if rr < cfg.min_rr:
        return _c("plan", False, f"R:R {rr:.2f} < {cfg.min_rr:.2f}")
    return _c("plan", True, f"SL a {frac:.2%}, R:R {rr:.2f}")


def check_freshness(p: PlanRequest, m: MarketContext, cfg: RiskConfig) -> Check:
    """El plan es reciente y sigue siendo ejecutable al precio actual (no cruzó SL ni TP1 y
    mantiene el R:R mínimo desde ahí)."""
    age = (m.now - p.asof) / m.bar_ms
    if age > cfg.max_plan_age_bars:
        return _c("vigencia", False,
                  f"plan de hace {age:.1f} velas (máx. {cfg.max_plan_age_bars:g})")
    px = m.last_price
    if px is None:
        return _c("vigencia", True, f"plan de hace {age:.1f} velas; sin precio actual")
    if (px - p.sl) * p.side <= 0:
        return _c("vigencia", False, f"el precio {px:,.2f} ya cruzó el SL")
    if p.tp and (px - p.tp[0]) * p.side >= 0:
        return _c("vigencia", False, f"el precio {px:,.2f} ya alcanzó el TP1")
    if p.tp:
        rr = (p.tp[0] - px) * p.side / ((px - p.sl) * p.side)
        if rr < cfg.min_rr:
            return _c("vigencia", False, f"R:R al precio actual {rr:.2f} < {cfg.min_rr:.2f}")
    return _c("vigencia", True, f"plan de hace {age:.1f} velas; precio {px:,.2f}")


def check_daily_loss(a: AccountState, cfg: RiskConfig) -> Check:
    loss = 1 - a.equity / a.day_start_equity if a.day_start_equity > 0 else 1.0
    ok = loss < cfg.max_daily_loss
    return _c("pérdida diaria", ok,
              f"resultado del día {-loss:+.2%} (límite −{cfg.max_daily_loss:.2%})")


def check_weekly_loss(a: AccountState, cfg: RiskConfig) -> Check:
    loss = 1 - a.equity / a.week_start_equity if a.week_start_equity > 0 else 1.0
    ok = loss < cfg.max_weekly_loss
    return _c("pérdida semanal", ok,
              f"resultado de la semana {-loss:+.2%} (límite −{cfg.max_weekly_loss:.2%})")


def check_open_trades(p: PlanRequest, a: AccountState, cfg: RiskConfig) -> Check:
    n, same = len(a.open_symbols), a.open_symbols.count(p.symbol)
    if n >= cfg.max_open_trades:
        return _c("operaciones abiertas", False, f"{n} abiertas (máx. {cfg.max_open_trades})")
    if same >= cfg.max_open_per_symbol:
        return _c("operaciones abiertas", False,
                  f"{same} abiertas en {p.symbol} (máx. {cfg.max_open_per_symbol})")
    return _c("operaciones abiertas", True, f"{n} abiertas")


def check_cooldown(a: AccountState, m: MarketContext, cfg: RiskConfig) -> Check:
    if a.consecutive_losses < cfg.max_consecutive_losses or a.last_loss_t is None:
        return _c("enfriamiento", True, f"{a.consecutive_losses} pérdidas seguidas")
    left = a.last_loss_t + cfg.cooldown_ms - m.now
    if left > 0:
        return _c("enfriamiento", False, f"{a.consecutive_losses} pérdidas seguidas: pausa "
                  f"{left / 3_600_000:.1f} h más")
    return _c("enfriamiento", True, "enfriamiento cumplido")


def check_event(m: MarketContext) -> Check:
    """Ventana de evento: `calendar` (blackout) o `context` (pausa); cualquiera veta."""
    why = [r for on, r in ((m.blackout, m.blackout_reason or "ventana de evento (calendario)"),
                           (m.event_pause, m.pause_reason or "pausa por evento (contexto)")) if on]
    return _c("evento", not why, "; ".join(why) or "sin ventana de evento")


def check_data(m: MarketContext, cfg: RiskConfig) -> Check:
    if m.last_close_t is None:
        return _c("datos", False, "sin velas cerradas")
    age = (m.now - m.last_close_t) / m.bar_ms
    if age > cfg.max_data_age_bars:
        return _c("datos", False, f"datos obsoletos: última vela cerró hace {age:.1f} velas")
    bad_crit = [k for k in cfg.critical_agents if m.agent_status.get(k, "no_data") != "ok"]
    if bad_crit:
        return _c("datos", False, f"agentes críticos sin estado ok: {', '.join(bad_crit)}")
    degraded = sorted(k for k, s in m.agent_status.items() if s == "degraded")
    if len(degraded) > cfg.max_degraded_agents:
        return _c("datos", False, f"{len(degraded)} agentes degradados: {', '.join(degraded)}")
    return _c("datos", True, f"última vela hace {age:.1f} velas; degradados: {len(degraded)}")
