"""T83 · Caos sin red: cada fallo lleva el carril a estado seguro (sin órdenes vivas, bloqueado
o con kill-switch) y queda registrado en `lane.events`.

Y la garantía central: **ninguna orden llega al exchange sin una `HftDecision` sellada, aprobada
y vigente** (el bróker la comprueba en cada envío durante una sesión con todos los fallos)."""

from __future__ import annotations

import random

import pytest

from eim.execution.broker import OrderRejected, OrderSpec, RateLimited
from eim.execution.gateway import HftGateway
from eim.execution.sim_broker import SimBroker
from eim.risk.hft_models import HftDecision
from tests.hft.hft_helpers import ASK, BID, CFG, SYM, T0, order, rig


def _kinds(r) -> list[str]:
    return [e.kind for e in r.lane.events]


def _quotes(r, n: int = 2) -> list[HftDecision]:
    ds = [r.submit(order(i=f"q{i}", price=BID - i * 0.1)) for i in range(n)]
    assert all(d.approved for d in ds) and len(r.sim.open_orders(SYM)) == n
    return ds


def _tick(r, **kw) -> list[str]:
    return r.lane.tick(r.mkt(**kw), r.clock())


# --- datos, libro, reloj y latido ----------------------------------------------------------
@pytest.mark.parametrize("fault, rule", [
    (dict(age=1_500), "datos"),                                # corte del WebSocket de mercado
    (dict(synced=False, issue="hueco de pu"), "libro"),       # hueco de secuencia
    (dict(offset=900.0), "reloj"),                            # reloj desviado
])
def test_market_faults_cancel_everything_and_block(fault, rule):
    r = rig()
    _quotes(r)
    acts = _tick(r, **fault)
    r.pump()
    assert acts and r.sim.open_orders(SYM) == [] and r.ledger.live(SYM) == []
    assert _kinds(r)[:2] == ["bloqueo", "cancelar_todo"] and rule in r.lane.events[0].detail
    d = r.submit(order(i="nueva"), **fault)
    assert not d.approved and d.rule == rule
    _tick(r)                                                   # se arregla (resincroniza)
    assert _kinds(r)[-1] == "desbloqueo" and r.submit(order(i="otra")).approved


def test_dead_man_cancels_when_the_strategy_stops_beating():
    r = rig()
    _quotes(r)
    r.clock.advance(CFG.deadman_ms + 1)
    _tick(r)
    r.pump()
    assert r.sim.open_orders(SYM) == [] and "hombre muerto" in r.lane.events[0].detail


class CountdownSim(SimBroker):
    """Simulado con el hombre muerto del exchange (`countdownCancelAll`) registrado."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.countdowns: list[tuple[str, int]] = []

    def countdown_cancel_all(self, symbol: str, ms: int) -> None:
        self.countdowns.append((symbol, ms))


def test_exchange_countdown_is_renewed_only_while_healthy():
    r = rig(sim=CountdownSim(min_notional=50.0))
    for _ in range(4):                                         # cada 5 s (15 s / 3)
        r.lane.heartbeat(r.clock())
        _tick(r)
        r.clock.advance(5_000)
    assert r.sim.countdowns == [(SYM, CFG.exchange_countdown_ms)] * 4
    r.clock.advance(CFG.deadman_ms)                            # la estrategia se calla
    _tick(r)
    assert len(r.sim.countdowns) == 4                          # ya no se renueva: vencerá


# --- flujo de usuario ------------------------------------------------------------------------
def test_user_stream_cut_blocks_and_reconciliation_recovers_the_lost_fill():
    r = rig()
    _quotes(r)
    r.stream.connected = False
    r.lane.set_user_stream(False, r.clock())
    r.sim.set_price(SYM, BID - 0.05)                           # casa q0; el evento se pierde
    assert r.stream.lost > 0 and r.ledger.position(SYM) == 0
    _tick(r)
    r.clock.advance(3_000)
    rep = r.lane.recon.run(SYM)
    assert rep.ok and r.ledger.position(SYM) == pytest.approx(0.001)
    assert not r.engine.lane_kill.active and r.sim.open_orders(SYM) == []
    assert "flujo de usuario" in r.lane.events[1].detail


# --- rechazos del exchange ---------------------------------------------------------------------
def test_post_only_that_would_cross_is_vetoed_or_rejected():
    r = rig()
    assert r.submit(order(price=ASK)).rule == "orden"          # el riesgo lo ve antes
    r.sim.set_price(SYM, BID - 1.0)                            # el libro se movió en vuelo
    d = r.submit(order(i="tarde"))
    assert d.approved and r.ledger.orders[d.client_id].status == "RECHAZADA"
    assert r.ex.rejections[-1][1:] == (-5022, "post-only que casaría como taker")
    assert r.sim.position(SYM).qty == 0 and r.ledger.account(SYM, BID, T0).orders_10s == 1


def test_min_notional_is_vetoed_before_sending():
    """(El rechazo `-4164` del exchange, si su mínimo es mayor, está en test_hft_execution.)"""
    r = rig()
    d = r.submit(order(price=40_000.0), bid=40_000.0, ask=40_000.1)
    assert d.rule == "tamaño" and r.sim.open_orders(SYM) == []


class LimitedSim(SimBroker):
    """Responde con 429 (o 418) a los envíos mientras `until` esté por llegar."""

    def __init__(self, status: int, clock, wait: int, **kw) -> None:
        super().__init__(**kw)
        self.status, self.clock, self.wait = status, clock, wait
        self.sent = 0
        self.until: int | None = None

    def post_order(self, spec: OrderSpec):
        self.sent += 1
        if self.until is None:
            self.until = self.clock() + self.wait
            raise RateLimited(f"HTTP {self.status}", self.status, self.until)
        return super().post_order(spec)


def test_429_backs_off_and_nothing_is_sent_until_it_passes():
    r = rig()
    sim = LimitedSim(429, r.clock, 1_000, min_notional=50.0)
    sim.set_price(SYM, (BID + ASK) / 2)
    r.ex.broker = sim
    assert r.submit(order(i="a")).approved and sim.sent == 1
    assert r.ledger.orders[next(iter(r.ledger.orders))].status == "DESCONOCIDA"
    b = r.submit(order(i="b"))
    assert not b.approved and b.rule == "límite del exchange" and sim.sent == 1
    r.clock.advance(1_001)
    r.lane.heartbeat(r.clock())
    assert r.submit(order(i="c", now=r.clock())).approved and sim.sent == 2


def test_418_trips_the_lane_kill_switch_until_manual_reset():
    r = rig()
    sim = LimitedSim(418, r.clock, 120_000, min_notional=50.0)
    sim.set_price(SYM, (BID + ASK) / 2)
    r.ex.broker = sim
    r.submit(order(i="a"))
    _tick(r)
    ks = r.engine.lane_kill
    assert ks.active and ks.state()["by"] == "regla:hft_418" and "kill" in _kinds(r)
    with pytest.raises(PermissionError):
        ks.deactivate(r.clock(), by="regla:auto")
    r.clock.advance(120_001)
    r.lane.heartbeat(r.clock())
    assert r.submit(order(i="b", now=r.clock())).rule == "kill-switch HFT"   # pasó el ban
    ks.deactivate(r.clock(), by="manual", reason="ban vencido y causa entendida")
    assert r.submit(order(i="c", now=r.clock())).approved


# --- fills parciales, doble envío y divergencia ----------------------------------------------
def test_double_send_after_a_restart_creates_no_second_order():
    r = rig()
    d = r.submit(order())
    fresh = rig(sim=r.sim)                                     # proceso nuevo, mismo exchange
    fresh.clock.t = r.clock()
    HftGateway(r.engine, fresh.ex).submit(d, r.clock())        # la misma decisión otra vez
    assert len(r.sim.open_orders(SYM)) == 1
    assert fresh.ledger.orders[d.client_id].state.client_id == d.client_id


def test_divergence_trips_both_kill_switches_and_flattens_with_a_decision():
    r = rig()
    r.submit(order(purpose="take", tif="IOC", price=ASK, qty=0.002))
    _quotes(r, 1)
    r.sim._fill(SYM, 1, 0.001, BID)                            # alguien más tocó la posición
    rep = r.lane.recon.run(SYM)
    assert not rep.ok and rep.kill and r.engine.kill_switch.active and r.engine.lane_kill.active
    assert r.engine.kill_switch.state()["by"] == "regla:hft_reconciliacion"
    acts = _tick(r)
    r.pump()
    assert any("cierre" in a for a in acts) and r.sim.open_orders(SYM) == []
    flat = [d for d in r.sink if d.order.purpose == "flatten"]
    assert flat and flat[-1].approved and flat[-1].reducing
    assert r.ledger.position(SYM) == 0                          # el carril cerró lo suyo
    assert r.submit(order(i="nueva")).rule == "kill-switch"    # y no abre nada más


def test_silent_exchange_trips_the_kill_switch():
    r = rig()

    class Down(SimBroker):
        def position(self, symbol):
            from eim.execution.broker import NetworkError
            raise NetworkError("sin red")
    r.ex.broker = Down()
    r.lane.recon.run(SYM)
    r.clock.advance(CFG.recon_max_silence_ms)
    rep = r.lane.recon.run(SYM)
    assert rep.kill and r.engine.lane_kill.active


# --- la garantía central -----------------------------------------------------------------------
class Auditor(SimBroker):
    """Exchange que, en cada envío, exige una decisión sellada, aprobada y vigente."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.engine = None
        self.clock = None
        self.decisions: dict[str, HftDecision] = {}
        self.audited = 0

    def post_order(self, spec: OrderSpec):
        d = self.decisions.get(spec.client_id)
        assert d is not None, f"orden {spec.client_id} sin decisión de riesgo"
        self.engine.verify_hft(d, self.clock())               # vigente, sellada, aprobada
        o = d.order
        assert (spec.symbol, spec.side, spec.qty, spec.reduce_only, spec.kind) == (
            o.symbol, o.side, o.qty, o.reduce_only, o.kind)
        self.audited += 1
        return super().post_order(spec)


def test_no_order_ever_reaches_the_exchange_without_a_valid_decision():
    rnd = random.Random(83)
    sim = Auditor(min_notional=50.0, fill_cap=0.002)
    r = rig(sim=sim, cfg=CFG.model_copy(update={"max_consecutive_losses": 10_000}))  # sin pausa
    sim.engine, sim.clock = r.engine, r.clock
    r.engine._sink = lambda d: sim.decisions.__setitem__(d.client_id, d)  # el registro
    faults = [dict(), dict(age=2_000), dict(synced=False), dict(offset=800.0)]
    px = (BID + ASK) / 2
    for i in range(400):
        r.clock.advance(rnd.choice((50, 120, 400, 1_500)))
        if rnd.random() < 0.9:
            r.lane.heartbeat(r.clock())
        px = round(px + rnd.choice((-0.3, -0.1, 0.0, 0.1, 0.3)), 1)
        r.move(px)
        fault = rnd.choice(faults) if rnd.random() < 0.2 else {}
        bid, ask = round(px - 0.05, 2), round(px + 0.05, 2)
        side = rnd.choice((1, -1))
        kind = rnd.random()
        if kind < 0.6:
            o = order(i=f"o{i}", side=side, price=round(px - 0.15 * side, 2), now=r.clock())
        elif kind < 0.75:
            o = order(i=f"o{i}", side=side, purpose="take", tif="IOC", now=r.clock(),
                      price=round(px + 0.1 * side, 2))
        else:
            pos = r.ledger.position(SYM)
            o = order(i=f"o{i}", side=-1 if pos > 0 else 1, qty=max(abs(pos), 0.001),
                      purpose="exit", reduce_only=True, now=r.clock(),
                      price=round(px + 0.15 * (1 if pos > 0 else -1), 2))
        try:
            r.submit(o, bid=bid, ask=ask, **fault)
        except OrderRejected:
            pass
        if rnd.random() < 0.3 and (live := r.ledger.live(SYM)):
            r.lane.cancel(rnd.choice(live).spec.client_id, r.mkt(bid=bid, ask=ask), r.clock())
        r.lane.tick(r.mkt(bid=bid, ask=ask, **fault), r.clock())
        if i % 25 == 0:
            r.lane.recon.run(SYM)
            if r.engine.kill_switch.active or r.engine.lane_kill.active:
                break
    assert sim.audited > 50                                    # la sesión sí envió órdenes
    assert r.lane.decisions >= sim.audited
