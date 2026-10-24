"""Reglas del riesgo HFT (T83): funciones puras que devuelven `Check`; aprobar exige todas ok.

Dos caminos. Una orden que **reduce** de verdad (reduce-only, del lado contrario a la posición y
sin pasarse) solo pasa las reglas de la orden y del exchange: cerrar inventario debe poder
hacerse con el libro obsoleto, el reloj desviado o el kill-switch activo. Cualquier otra orden
pasa además los **bloqueos** (kill-switch global y del carril, datos, libro, reloj, hombre
muerto, flujo de usuario) y los límites de inventario, exposición, tamaño, pérdidas y tasas.
`blockers` son los bloqueos solos: el carril los vigila fuera de las decisiones y, si alguno
salta con órdenes vivas, cancela todo (`eim/execution/hft_lane.py`).
"""

from __future__ import annotations

import math

from eim.risk.authority import expiry_reason, route_reason
from eim.risk.hft_config import HftRiskConfig
from eim.risk.hft_models import AUTHORITY, HftAccount, HftMarket, HftOrder
from eim.risk.models import Check

Kill = tuple[bool, str]                    # (activo, motivo)


def _c(rule: str, ok: bool, detail: str) -> Check:
    return Check(rule=rule, ok=ok, detail=detail)


def reduces(o: HftOrder, a: HftAccount, tol: float = 1e-12) -> bool:
    """Reduce-only del lado contrario a la posición y sin pasarse de ella."""
    return o.reduce_only and o.side * a.position < 0 and o.qty <= abs(a.position) + tol


def check_route(o: HftOrder, now: int, cfg: HftRiskConfig, m: HftMarket) -> list[Check]:
    why = route_reason(o.source, AUTHORITY, "hft_rules")
    late = expiry_reason(o.expires_at, now)
    sym = o.symbol in cfg.symbols and m.symbol == o.symbol
    return [_c("fuente", why is None, why or f"{o.source} {o.source_version} → {AUTHORITY}"),
            _c("caducidad", late is None, late or "vigente"),
            _c("modo", o.mode.value in cfg.allowed_modes, f"modo {o.mode.value}" + (
                "" if o.mode.value in cfg.allowed_modes else " no permitido")),
            _c("símbolo", sym, o.symbol if sym else f"{o.symbol} no habilitado o libro de "
               f"{m.symbol}")]


def check_order(o: HftOrder, m: HftMarket, cfg: HftRiskConfig) -> Check:
    """Forma de la orden: tipo y vigencia coherentes con su propósito, precio cerca del mid y
    post-only que no cruce (el exchange la rechazaría y gastaría una orden de la tasa)."""
    if o.side not in (1, -1) or not (math.isfinite(o.qty) and o.qty > 0):
        return _c("orden", False, "sin lado o cantidad ≤ 0")
    if o.purpose in ("exit", "flatten") and not o.reduce_only:
        return _c("orden", False, f"«{o.purpose}» debe ser reduce-only")
    if o.kind == "MARKET":
        ok = o.purpose == "flatten"
        return _c("orden", ok, "a mercado (cierre)" if ok else "a mercado solo para cerrar")
    if o.price is None or not (math.isfinite(o.price) and o.price > 0):
        return _c("orden", False, "límite sin precio válido")
    want = {"quote": "GTX", "exit": "GTX", "take": "IOC"}.get(o.purpose)
    if want and o.tif != want:
        return _c("orden", False, f"«{o.purpose}» exige {want}, no {o.tif}")
    mid = m.mid
    if mid is None:
        return _c("orden", False, "sin precio medio del libro")
    dev = abs(o.price / mid - 1) * 1e4
    if dev > cfg.max_price_dev_bps:
        return _c("orden", False, f"precio a {dev:.1f} pb del mid (máx. {cfg.max_price_dev_bps:g})")
    if o.tif == "GTX" and ((o.side > 0 and o.price >= (m.best_ask or math.inf))
                           or (o.side < 0 and o.price <= (m.best_bid or 0.0))):
        return _c("orden", False, "post-only que cruzaría el libro (sería taker)")
    return _c("orden", True, f"{o.purpose} {o.tif} a {dev:.1f} pb del mid")


def check_exchange(a: HftAccount, now: int) -> Check:
    if a.banned:
        return _c("límite del exchange", False, "IP bloqueada por el exchange (418)")
    if a.rate_limited_until is not None and now < a.rate_limited_until:
        return _c("límite del exchange", False, f"en espera por 429 "
                  f"{(a.rate_limited_until - now) / 1000:.1f} s más")
    return _c("límite del exchange", True, "sin límite de tasa activo")


def check_rate(a: HftAccount, cfg: HftRiskConfig, reducing: bool) -> Check:
    """Órdenes por ventana (+ esta). Reduce-only: hasta `reduce_rate_frac` del límite real."""
    if reducing:
        f = cfg.reduce_rate_frac
        lim10, lim60 = int(f * cfg.exchange_orders_10s), int(f * cfg.exchange_orders_60s)
    else:
        lim10, lim60 = cfg.max_orders_10s, cfg.max_orders_60s
    ok = a.orders_10s + 1 <= lim10 and a.orders_60s + 1 <= lim60
    return _c("tasa de órdenes", ok, f"{a.orders_10s}/10 s (máx. {lim10}), "
              f"{a.orders_60s}/min (máx. {lim60})")


def cancel_rate_ok(a: HftAccount, cfg: HftRiskConfig) -> bool:
    """Las cancelaciones no necesitan decisión (solo reducen), pero cuentan en su tasa."""
    return a.cancels_10s < cfg.max_cancels_10s and a.cancels_60s < cfg.max_cancels_60s


def blockers(m: HftMarket, a: HftAccount, cfg: HftRiskConfig, now: int, kill: Kill,
             lane_kill: Kill) -> list[Check]:
    """Bloqueos que vetan toda orden que no reduzca (y, con órdenes vivas, cancelan todo)."""
    age = m.book_age_ms(now)
    off = m.clock_offset_ms
    hb = math.inf if a.heartbeat_t is None else now - a.heartbeat_t
    return [
        _c("kill-switch", not kill[0], f"activo: {kill[1]}" if kill[0] else "inactivo"),
        _c("kill-switch HFT", not lane_kill[0],
           f"activo: {lane_kill[1]}" if lane_kill[0] else "inactivo"),
        _c("datos", age <= cfg.max_book_age_ms, f"libro de hace {age:.0f} ms "
           f"(máx. {cfg.max_book_age_ms})" if math.isfinite(age) else "sin libro"),
        _c("libro", m.book_synced, "verificado" if m.book_synced else
           f"inconsistente: {m.book_issue or 'hueco de secuencia'} (hasta resincronizar)"),
        _c("reloj", off is not None and abs(off) <= cfg.max_clock_skew_ms,
           "reloj sin medir" if off is None else
           f"desvío {off:+.0f} ms (máx. ±{cfg.max_clock_skew_ms})"),
        _c("hombre muerto", hb <= cfg.deadman_ms, "sin latido de la estrategia"
           if not math.isfinite(hb) else f"último latido hace {hb:.0f} ms (máx. {cfg.deadman_ms})"),
        _c("flujo de usuario", a.user_stream_ok, "conectado" if a.user_stream_ok else
           "desconectado: los fills no llegan por evento"),
    ]


def check_limits(o: HftOrder, m: HftMarket, a: HftAccount, cfg: HftRiskConfig,
                 now: int) -> list[Check]:
    """Tamaño, inventario, exposición, órdenes vivas, pérdidas y enfriamiento (no reduce)."""
    px = o.price or m.mid or 0.0
    notional = o.qty * px
    long_q = a.position + a.live_buy_qty + (o.qty if o.side > 0 else 0.0)
    short_q = a.position - a.live_sell_qty - (o.qty if o.side < 0 else 0.0)
    worst = abs(long_q) if o.side > 0 else abs(short_q)    # si todo lo vivo de ese lado llena
    net = abs(a.position + a.live_buy_qty - a.live_sell_qty + o.side * o.qty) * px
    cap = cfg.capital_usd
    losses = [(k, -v / cap, lim) for k, v, lim in (
        ("sesión", a.pnl_session, cfg.max_session_loss_frac),
        ("hora", a.pnl_hour, cfg.max_hour_loss_frac),
        ("día", a.pnl_day, cfg.max_day_loss_frac))]
    bad = [f"{k} {-x:+.2%} (límite −{lim:.2%})" for k, x, lim in losses if x >= lim]
    dd = a.drawdown_day / cap
    cool = a.consecutive_losses >= cfg.max_consecutive_losses and a.last_loss_t is not None \
        and now < a.last_loss_t + cfg.cooldown_ms
    size_ok = (o.qty <= cfg.max_order_qty and notional <= cfg.max_order_notional
               and notional >= cfg.min_notional_usd)
    return [
        _c("tamaño", size_ok, f"{o.qty:g} = {notional:,.0f} USD (máx. {cfg.max_order_qty:g} y "
           f"{cfg.max_order_notional:,.0f}; mín. {cfg.min_notional_usd:,.0f} USD)"),
        _c("inventario", worst <= cfg.max_position_qty + 1e-12
           and worst * px <= cfg.max_position_notional,
           f"peor caso {worst:g} = {worst * px:,.0f} USD (máx. {cfg.max_position_qty:g} y "
           f"{cfg.max_position_notional:,.0f})"),
        _c("exposición neta", net <= cfg.max_net_exposure_notional,
           f"{net:,.0f} USD (máx. {cfg.max_net_exposure_notional:,.0f})"),
        _c("órdenes vivas", a.live_orders + 1 <= cfg.max_live_orders,
           f"{a.live_orders} vivas (máx. {cfg.max_live_orders})"),
        _c("pérdidas", not bad, "; ".join(bad) or
           f"sesión {a.pnl_session:+.2f}, hora {a.pnl_hour:+.2f}, día {a.pnl_day:+.2f} USD"),
        _c("caída intradía", dd < cfg.max_intraday_drawdown_frac,
           f"{dd:.2%} desde el máximo del día (límite {cfg.max_intraday_drawdown_frac:.2%})"),
        _c("enfriamiento", not cool, f"{a.consecutive_losses} pérdidas seguidas" + (
            f": pausa {(a.last_loss_t + cfg.cooldown_ms - now) / 60_000:.1f} min más"
            if cool and a.last_loss_t is not None else "")),
    ]


def evaluate(o: HftOrder, m: HftMarket, a: HftAccount, cfg: HftRiskConfig, now: int,
             kill: Kill, lane_kill: Kill) -> tuple[list[Check], bool]:
    """Todas las reglas que aplican (para listar todos los motivos) y si la orden reduce."""
    reducing = reduces(o, a)
    checks = [*check_route(o, now, cfg, m), check_order(o, m, cfg), check_exchange(a, now),
              check_rate(a, cfg, reducing)]
    if reducing:
        checks.append(_c("reduce", True, f"reduce la posición {a.position:g} en {o.qty:g}: "
                         "pasa con bloqueos y kill-switch"))
    elif o.reduce_only:
        checks.append(_c("reduce", False, f"reduce-only que no reduce (posición {a.position:g})"))
    else:
        checks += blockers(m, a, cfg, now, kill, lane_kill) + check_limits(o, m, a, cfg, now)
    return checks, reducing
