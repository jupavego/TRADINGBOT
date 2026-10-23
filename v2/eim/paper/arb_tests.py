"""Pruebas del arbitraje en el bróker simulado (T45, modo SIMULADO): el mismo ejecutor, riesgo,
puerta y reconciliación de T45 sobre un exchange en memoria (`arb_sim`, un venue por mercado)
movido por velas REALES de 1 h de Binance (spot y perpetuo) y el funding realizado. Sin cuenta
de Binance ni órdenes reales.

Escenarios (los de la aceptación de T45), cada uno con su exchange y su kill-switch propios:
1. `carry`: abrir (riesgo → puerta → dos patas), mantener `hold_h` horas cobrando el funding de
   cada liquidación real (reconciliación y gestión cada hora: margen, liquidación, funding real
   vs esperado, rebalanceo) y cerrar al acabar la ventana.
2. `fail`: futuros rechaza la orden → se deshace la compra spot → posición neta cero.
3. `cut`: la red cae tras comprar spot; al volver, la reconciliación no deja ninguna huérfana.
El plan es el del carry en vivo (T43: tenencia 90 d, funding esperado = media de las últimas 21
liquidaciones); la prueba lo cierra antes porque la ventana de datos se acaba.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eim.core import Mode
from eim.data.arb_sim_data import H_MS, SimSeries
from eim.execution.arb_book import ACTIVE, ArbPosition, position_row
from eim.execution.arb_executor import ArbExecutor
from eim.execution.arb_recon import ArbReconciler
from eim.execution.arb_runner import ArbAutopilot, decision_row
from eim.execution.arb_sim import SimVenue
from eim.execution.arb_sim_brokers import SimFuturesBroker, SimSpotBroker
from eim.execution.gateway import ArbGateway
from eim.risk import KillSwitch
from eim.risk.arb_config import ArbRiskConfig, load_arb_config
from eim.risk.arb_engine import ArbRiskEngine
from eim.risk.arb_models import ArbLegPlan, ArbPlan

SIM_VERSION = "risk_arb_sim_v1"
CARRY_H = 2160.0                    # tenencia del carry en vivo (T43)


class SimClock:
    def __init__(self, t: int) -> None:
        self.t = t

    def __call__(self) -> int:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += int(s * 1000)


@dataclass
class Rig:
    s: SimSeries
    sv: SimVenue                    # spot
    fv: SimVenue                    # futuros USDⓈ-M
    clock: SimClock
    ex: ArbExecutor
    engine: ArbRiskEngine
    gw: ArbGateway
    recon: ArbReconciler
    pilot: ArbAutopilot
    journal: list[dict[str, Any]] = field(default_factory=list)

    def at(self, i: int) -> None:
        """Avanza a la hora de cierre de la vela `i` con sus precios reales."""
        self.clock.t = max(self.clock.t, self.s.t[i] + H_MS)
        self.sv.set_mid(self.s.symbol, self.s.spot[i])
        self.fv.set_mid(self.s.symbol, self.s.fut[i])

    def down(self, on: bool) -> None:
        self.sv.down = self.fv.down = on


def _rig(s: SimSeries, i: int, cfg: ArbRiskConfig) -> Rig:
    clock = SimClock(s.t[i] + H_MS)
    sv = SimVenue(depth={s.symbol: 3.0}, clock=clock)      # libro spot más fino que el perpetuo
    fv = SimVenue(depth={s.symbol: 20.0}, clock=clock)
    kill = KillSwitch()                                     # propio de cada escenario
    journal: list[dict[str, Any]] = []
    ex = ArbExecutor(SimSpotBroker(sv), SimFuturesBroker(fv), kill, sleep=clock.sleep,
                     clock=clock, journal=lambda k, d: journal.append({"t": clock(), "kind": k,
                                                                       **d}))
    engine = ArbRiskEngine(cfg, lambda d: journal.append(
        {"t": clock(), "kind": "riesgo", **decision_row(d)}), kill)
    recon = ArbReconciler(ex, cfg)
    pilot = ArbAutopilot(ex, recon, engine, store=None, journal=lambda k, d: None,  # type: ignore
                         clock=clock)
    rig = Rig(s, sv, fv, clock, ex, engine, ArbGateway(engine, ex), recon, pilot, journal)
    rig.at(i)
    return rig


def carry_plan(r: Rig, notional: float) -> ArbPlan:
    """Plan del carry en vivo con los precios del momento: tenencia 90 d y funding esperado =
    media de las últimas liquidaciones reales; costos = comisiones VIP 0 + diferencial."""
    s, now = r.s, r.clock()
    s_px, f_px = r.sv.mids[s.symbol], r.fv.mids[s.symbol]
    rate = sum(s.funding_hist) / len(s.funding_hist) if s.funding_hist else 0.0
    side_cost = (r.sv.spot_fee + r.fv.fut_fee) * 1e4 + r.sv.spread_bps
    gross = rate * CARRY_H / 8 * 1e4
    qty = notional / s_px
    return ArbPlan(
        arb_id=f"sim|carry|{s.symbol}|{now}", strategy="funding_carry",
        variant="largo spot / corto perpetuo", asset=s.symbol.removesuffix("USDT"),
        legs=(ArbLegPlan(market="spot", symbol=s.symbol, side=1, ref_price=s_px,
                         depth_frac=qty / 3.0),
              ArbLegPlan(market="usdm", symbol=s.symbol, side=-1, ref_price=f_px,
                         depth_frac=qty / 20.0)),
        qty=qty, notional=notional, leverage=3,
        net_edge=(gross - 2 * side_cost) / 1e4 * notional, net_bps=gross - 2 * side_cost,
        score=0.0, annualized=None, horizon_h=CARRY_H, funding_rate=rate, interval_h=8.0,
        exit_cost_bps=side_cost, asof=now, valid_until=now + 15_000,
        source=f"bróker simulado · precios reales {s.sources['spot']} / {s.sources['futuros']}",
        mode=Mode.SIMULADO)


def _open(r: Rig, notional: float) -> tuple[ArbPosition | None, dict[str, Any]]:
    now = r.clock()
    plan = carry_plan(r, notional)
    d = r.engine.evaluate(plan, r.pilot.account(now, None), now,
                          proposal=plan.as_proposal("ops.smoke", "escenarios T45 en papel"))
    if not d.approved:
        return None, decision_row(d)
    return r.ex.positions[r.gw.submit(d, now)], decision_row(d)


def _check(label: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"label": label, "ok": bool(ok), "detail": detail}


def _flat(r: Rig, pos: ArbPosition | None) -> dict[str, Any]:
    """Neto en el exchange: futuros a cero y spot reducido a polvo bajo el mínimo de orden."""
    sym = r.s.symbol
    fut = r.fv.pos.get(sym, [0.0])[0]
    spot = r.sv.balances.get(sym.removesuffix("USDT"), 0.0)
    dust = spot * r.sv.mids[sym] < 5.0
    left = [o.client_id for v in (r.sv, r.fv) for o, _, _ in v.orders.values() if o.is_open]
    return _check("Sin posición huérfana: futuros 0 y spot en polvo, sin órdenes abiertas",
                  fut == 0 and dust and not left,
                  f"futuros {fut:+.6g} · spot {spot:.8g} (≈ {spot * r.sv.mids[sym]:.2f} USD)"
                  f" · órdenes abiertas {len(left)}")


def _result(sid: str, title: str, r: Rig, pos: ArbPosition | None, checks: list[dict],
            t0: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    orders = [] if pos is None else [
        {"t": o.t, "market": o.market, "side": o.side, "role": o.role, "qty": o.qty,
         "filled": o.filled, "avg": o.avg, "status": o.status, "price": o.price}
        for o in pos.orders]
    return {"id": sid, "title": title, "ok": all(c["ok"] for c in checks), "t0": t0,
            "t1": r.clock(), "checks": checks, "orders": orders,
            "position": position_row(pos) if pos is not None else None,
            "journal": r.journal[-60:], **(extra or {})}


def run_carry(s: SimSeries, cfg: ArbRiskConfig, hold_h: int, notional: float) -> dict[str, Any]:
    r = _rig(s, 0, cfg)
    t0 = r.clock()
    pos, d = _open(r, notional)
    checks = [_check("El riesgo aprueba la apertura (cuenta total, modo Simulado)",
                     d["approved"], "; ".join(d["reasons"]) or f"{d['qty']:.6g} {d['asset']}")]
    if pos is None:
        return _result("carry", "Carry: abrir, mantener y cerrar", r, pos, checks, t0)
    checks.append(_check("Dos patas abiertas y cubiertas", pos.status == "ABIERTA",
                         f"spot {pos.spot.held:+.6g} / futuros {pos.fut.held:+.6g}"))
    track: list[dict[str, Any]] = []
    min_liq, settled = 1.0, 0
    for i in range(1, min(hold_h, len(s.t) - 1) + 1):
        prev = r.clock()
        r.at(i)
        for t, rate in s.funding:
            if prev < t <= r.clock():
                r.fv.settle_funding(s.symbol, rate, t)
                settled += 1
        rep: dict[str, Any] = {"actions": []}
        r.recon.run(r.clock())
        r.pilot.manage(None, r.clock(), rep)
        min_liq = min(min_liq, pos.liq_move or 1.0)
        track.append({"t": r.clock(), "margin": pos.margin_equity, "liq_move": pos.liq_move,
                      "funding": pos.funding_received, "expected": pos.funding_expected,
                      "pnl": pos.pnl(r.sv.mids[s.symbol], r.fv.mids[s.symbol])})
        if pos.status not in ACTIVE:
            break
    held_h = (r.clock() - t0) / H_MS
    checks.append(_check(f"Mantenida {held_h:.0f} h con reconciliación horaria",
                         pos.status == "ABIERTA" and not r.fv.liquidations,
                         f"liquidación más cercana a {min_liq:.1%} · rebalanceos {pos.rebalances}"))
    checks.append(_check("Funding real cobrado en cada liquidación",
                         pos.funding_n == settled > 0,
                         f"{pos.funding_n} pagos: {pos.funding_received:+.4f} USD real vs "
                         f"{pos.funding_expected:+.4f} USD esperado"))
    pnl_open = pos.pnl(r.sv.mids[s.symbol], r.fv.mids[s.symbol])
    closed = r.ex.close(pos, "fin de la ventana de prueba")
    checks.append(_check("Cierre de las dos patas", closed and pos.status == "CERRADA",
                         pos.exit_reason))
    checks.append(_flat(r, pos))
    base = s.symbol.removesuffix("USDT")
    fees = sum(o.fee * (o.avg or 0.0) if o.fee_asset == base else o.fee for o in pos.orders)
    return _result("carry", "Carry: abrir, mantener y cerrar", r, pos, checks, t0, {
        "track": track, "pnl": pos.pnl(r.sv.mids[s.symbol], r.fv.mids[s.symbol]),
        "pnl_before_close": pnl_open, "fees_usd": fees, "settlements": settled,
        "note": (f"Resultado de {held_h:.0f} h: el carry necesita semanas para cubrir comisiones "
                 "de entrada y salida (T43: tenencia 90 d); aquí se cierra al acabar la ventana.")})


def run_fail(s: SimSeries, cfg: ArbRiskConfig, i: int, notional: float) -> dict[str, Any]:
    r = _rig(s, i, cfg)
    t0 = r.clock()
    r.fv.reject[s.symbol] = "Margin is insufficient. (rechazo simulado)"
    pos, d = _open(r, notional)
    checks = [_check("El riesgo aprueba la apertura", d["approved"],
                     "; ".join(d["reasons"]) or f"{d['qty']:.6g} {d['asset']}")]
    if pos is None:
        return _result("fail", "Pata fallida: deshacer la primera", r, pos, checks, t0)
    roles = [(o.role, o.market, o.status) for o in pos.orders]
    checks += [
        _check("Primero la pata menos líquida (spot) se ejecuta",
               bool(roles) and roles[0][:2] == ("abrir", "spot") and roles[0][2] == "FILLED"),
        _check("La pata de futuros se rechaza (con reintentos acotados)",
               any(x == ("cubrir", "usdm", "REJECTED") for x in roles),
               f"{sum(1 for x in roles if x[0] == 'cubrir')} intentos rechazados"),
        _check("Se deshace la pata spot", ("deshacer", "spot", "FILLED") in roles),
        _check("Pérdida de la pata incompleta dentro del tope",
               pos.incident_loss <= pos.max_leg_loss and not r.ex.kill.active,
               f"{pos.incident_loss:.4f} USD (tope {pos.max_leg_loss:.2f} USD = "
               f"{pos.max_leg_loss_bps:g} pb) · kill-switch "
               f"{'activo' if r.ex.kill.active else 'inactivo'}"),
        _check("Estado final: fallida con posición neta cero", pos.status == "FALLIDA",
               pos.exit_reason),
        _flat(r, pos)]
    return _result("fail", "Pata fallida: deshacer la primera", r, pos, checks, t0)


def run_cut(s: SimSeries, cfg: ArbRiskConfig, i: int, notional: float) -> dict[str, Any]:
    r = _rig(s, i, cfg)
    t0 = r.clock()

    def cut(v: SimVenue, o: Any) -> None:
        if o.side > 0 and o.filled > 0:
            r.down(True)
    r.sv.hooks.append(cut)
    pos, d = _open(r, notional)
    checks = [_check("El riesgo aprueba la apertura", d["approved"],
                     "; ".join(d["reasons"]) or f"{d['qty']:.6g} {d['asset']}")]
    if pos is None:
        return _result("cut", "Corte de red a mitad de la apertura", r, pos, checks, t0)
    r.sv.hooks.clear()
    checks.append(_check("Tras el corte la posición queda DESCUBIERTA (no se oculta)",
                         pos.status == "DESCUBIERTA",
                         f"spot {pos.spot.held:+.6g} / futuros {pos.fut.held:+.6g}"))
    during = r.recon.run(r.clock() + 30_000)
    checks.append(_check("La reconciliación detecta la desconexión y no actúa a ciegas",
                         not during.connected, "; ".join(during.issues)))
    r.clock.t += 120_000
    r.down(False)
    after = r.recon.run(r.clock())
    checks.append(_check("Al volver la red, la reconciliación corrige el descubierto",
                         pos.status in ("FALLIDA", "CERRADA"), "; ".join(after.actions)))
    checks.append(_flat(r, pos))
    return _result("cut", "Corte de red a mitad de la apertura", r, pos, checks, t0)


def run_all(s: SimSeries, hold_h: int = 48, notional: float = 1000.0,
            cfg: ArbRiskConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_arb_config(version=SIM_VERSION)
    n = len(s.t)
    hold = max(1, min(hold_h, n - 6))
    scen = [run_carry(s, cfg, hold, notional), run_fail(s, cfg, min(hold + 2, n - 1), notional),
            run_cut(s, cfg, min(hold + 4, n - 1), notional)]
    return {
        "mode": "SIMULADO", "symbol": s.symbol, "config": cfg.version, "notional": notional,
        "ok": all(x["ok"] for x in scen), "window": [s.t[0] + H_MS, s.t[-1] + H_MS],
        "series": {"spot": [[t + H_MS, p] for t, p in zip(s.t, s.spot, strict=True)],
                   "futures": [[t + H_MS, p] for t, p in zip(s.t, s.fut, strict=True)],
                   "funding": [[t, x] for t, x in s.funding]},
        "sources": s.sources, "scenarios": scen,
        "assumptions": ["Precios: cierres reales de velas de 1 h (spot y perpetuo); libro "
                        "simulado con ±1 pb alrededor del precio y profundidad fija.",
                        "Comisiones VIP 0 tomador: spot 0,10 % (compra cobrada en BTC), "
                        "futuros 0,05 %. Funding: tasas realizadas de Binance.",
                        "Sin cuenta de Binance ni órdenes reales: exchange en memoria."]}
