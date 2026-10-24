"""T83 · Ejecución HFT sobre el `Broker`: post-only, reduce-only, ids, fills por evento."""

from __future__ import annotations

import pytest

from eim.core import Mode
from eim.execution.broker import FILLED, LIMIT, PARTIAL, OrderSpec
from eim.execution.gateway import HftGateway, OrderIntent
from eim.execution.service import ExecutionService
from eim.execution.sim_broker import SimBroker
from eim.execution.user_stream import (
    SimUserStream,
    UserEvent,
    UserEventRouter,
    parse_user_event,
)
from eim.risk.hft_models import hft_client_id
from eim.risk.killswitch import KillSwitch
from tests.hft.hft_helpers import ASK, BID, SYM, order, rig


def test_quote_goes_out_as_post_only_and_rests():
    r = rig()
    d = r.submit(order())
    assert d.approved
    lo = r.ledger.orders[d.client_id]
    assert (lo.spec.kind, lo.spec.tif, lo.spec.price, lo.spec.reduce_only) == (LIMIT, "GTX", BID,
                                                                              False)
    assert lo.live and r.sim.open_orders(SYM)[0].client_id == d.client_id


def test_fill_arrives_by_event_and_moves_the_inventory():
    r = rig()
    d = r.submit(order())
    r.move(BID - 0.5)                                  # el precio baja y casa la compra
    lo = r.ledger.orders[d.client_id]
    assert lo.status == FILLED and not lo.live
    assert r.ledger.position(SYM) == pytest.approx(0.001)
    assert r.ledger.fees == pytest.approx(0.001 * BID * 0.0002)
    a = r.ledger.account(SYM, BID, r.clock())
    assert a.position == pytest.approx(0.001) and a.live_orders == 0 and a.orders_10s == 1


def test_partial_fill_then_idempotent_cancel():
    r = rig(fill_cap=0.001)
    d = r.submit(order(qty=0.003))
    r.move(BID - 0.5)
    lo = r.ledger.orders[d.client_id]
    assert lo.status == PARTIAL and r.ledger.position(SYM) == pytest.approx(0.001)
    assert r.ledger.account(SYM, BID, r.clock()).live_buy_qty == pytest.approx(0.002)
    assert r.ex.cancel(d.client_id) is True
    assert r.ex.cancel(d.client_id) is False           # ya pedida: no se repite
    r.pump()
    assert not lo.live and r.ledger.position(SYM) == pytest.approx(0.001)
    assert r.ex.cancel(d.client_id) is False           # cerrada: nada que hacer
    assert r.lane.recon.run(SYM).ok                    # libro del carril = exchange


def test_same_decision_twice_sends_one_order():
    r = rig()
    d = r.submit(order())
    gw = HftGateway(r.engine, r.ex)
    gw.submit(d, r.clock())                            # doble envío de la misma decisión
    assert len([o for o in r.sim.open_orders(SYM)]) == 1 and len(r.ledger.orders) == 1


def test_client_ids_are_deterministic_and_valid():
    a, b = hft_client_id("q1", SYM), hft_client_id("q1", SYM)
    assert a == b != hft_client_id("q2", SYM) and a.startswith("eih-") and len(a) <= 36


def test_reduce_only_exit_and_market_flatten():
    r = rig()
    r.submit(order(purpose="take", tif="IOC", price=ASK, qty=0.002))
    assert r.ledger.position(SYM) == pytest.approx(0.002)
    d = r.submit(order(i="x1", side=-1, qty=0.001, purpose="exit", reduce_only=True))
    assert d.approved and d.reducing and r.ledger.orders[d.client_id].spec.reduce_only
    f = r.submit(order(i="f1", side=-1, qty=0.002, kind="MARKET", price=None, purpose="flatten",
                       reduce_only=True))
    assert f.approved and r.ledger.orders[f.client_id].spec.kind == "MARKET"
    assert r.ledger.position(SYM) == 0 and r.sim.position(SYM).qty == 0


def test_cancel_all_touches_only_the_lane_orders():
    r = rig()
    r.sim.post_order(OrderSpec("eim-otro-carril-e", SYM, 1, LIMIT, qty=0.001, price=99_000.0))
    for i in range(3):
        r.submit(order(i=f"q{i}", price=BID - i * 0.1))
    assert r.ex.cancel_all(SYM) == 3
    r.pump()
    assert [o.client_id for o in r.sim.open_orders(SYM)] == ["eim-otro-carril-e"]


def test_rejections_are_recorded_without_retry():
    r = rig(min_notional=150.0)                        # el exchange exige más que la política
    d = r.submit(order())
    assert d.approved and r.ledger.orders[d.client_id].status == "RECHAZADA"
    assert r.ex.rejections == [(d.client_id, -4164, "nocional mínimo")]
    assert r.sim.open_orders(SYM) == []


# --- eventos del flujo de usuario de Binance --------------------------------------------------
OTU = {"e": "ORDER_TRADE_UPDATE", "E": 1_761_300_000_100, "T": 1_761_300_000_099, "o": {
    "s": "BTCUSDT", "c": "eih-abc", "S": "BUY", "o": "LIMIT", "f": "GTX", "q": "0.003",
    "p": "100000.0", "ap": "100000.0", "sp": "0", "x": "TRADE", "X": "PARTIALLY_FILLED",
    "i": 42, "l": "0.001", "z": "0.001", "L": "100000.0", "N": "USDT", "n": "0.02",
    "T": 1_761_300_000_099, "m": True, "R": False, "cp": False, "ot": "LIMIT", "rp": "0"}}
ACU = {"e": "ACCOUNT_UPDATE", "E": 1_761_300_000_101, "T": 1_761_300_000_100, "a": {
    "m": "ORDER", "B": [], "P": [{"s": "BTCUSDT", "pa": "0.001", "ep": "100000.0",
                                 "ps": "BOTH"}]}}


def test_binance_user_events_are_parsed():
    (ev,) = parse_user_event(OTU)
    assert (ev.kind, ev.exec_type, ev.last_qty, ev.last_price, ev.fee, ev.maker) == (
        "order", "TRADE", 0.001, 100_000.0, 0.02, True)
    st = ev.state
    assert (st.client_id, st.side, st.status, st.filled, st.qty) == ("eih-abc", 1, PARTIAL,
                                                                     0.001, 0.003)
    (acc,) = parse_user_event(ACU)
    assert (acc.kind, acc.symbol, acc.position) == ("account", "BTCUSDT", 0.001)
    assert parse_user_event({"e": "listenKeyExpired", "E": 1})[0].kind == "expired"
    assert parse_user_event({"e": "MARGIN_CALL", "E": 1})[0].kind == "other"


def test_a_fill_seen_by_event_and_by_query_counts_once():
    r = rig()
    d = r.submit(order(qty=0.003))
    st = r.ledger.orders[d.client_id].state
    from dataclasses import replace
    half = replace(st, status=PARTIAL, filled=0.001, avg_price=BID)
    r.lane.on_user_events([UserEvent("order", 1, 1, SYM, half, "TRADE", 0.001, BID, 0.02)])
    r.ledger.on_state(half)                            # la consulta trae lo mismo
    assert r.ledger.position(SYM) == pytest.approx(0.001)
    r.ledger.on_state(replace(st, status=FILLED, filled=0.003, avg_price=BID))
    r.ledger.on_state(half)                            # un estado viejo no retrocede
    assert r.ledger.position(SYM) == pytest.approx(0.003)
    assert r.ledger.orders[d.client_id].status == FILLED


# --- BACKLOG T30 (1): la entrada LIMIT viva se cancela en el evento de cierre ---------------
def test_t30_limit_entry_is_cancelled_when_the_position_closes():
    """Entrada LIMIT llenada a medias; el TP (o el SL) cierra la posición con la entrada aún
    viva. Antes esperaba a la siguiente reconciliación y, si el precio volvía, reabría; ahora el
    evento de cuenta dispara `sync` y la cancela en ese momento."""
    sim = SimBroker(fill_cap=0.001)
    sim.set_price(SYM, 70_100.0)
    svc = ExecutionService(sim, KillSwitch(), sleep=lambda _s: None)
    stream = SimUserStream(sim, lambda: 0)
    router = UserEventRouter(svc=svc)
    key = svc.place(OrderIntent(symbol=SYM, side=1, size=0.003, leverage=3, mode=Mode.SIMULADO,
                                plan_id="p1", entry=70_000.0, sl=69_000.0, tp=(73_000.0,),
                                entry_kind="LIMIT"))
    sim.set_price(SYM, 69_990.0)                       # llena 0,001 de la entrada
    stream.pump(router)
    assert svc.trades[key].filled == pytest.approx(0.001)
    sim.set_price(SYM, 73_100.0)                       # el TP cierra la posición…
    stream.pump(router)                                # …y el evento cancela la entrada YA
    tr = svc.trades[key]
    assert tr.status == "CERRADA" and tr.exit_reason == "TP" and router.errors == []
    assert not sim.order_by_id(tr.cid("e")).is_open
    sim.set_price(SYM, 69_990.0)                       # vuelve al precio de la entrada
    assert sim.position(SYM).qty == 0                  # no reabre una posición sin SL
    assert sim.open_orders(SYM) == []


def test_closed_orders_are_forgotten_after_a_minute():
    r = rig()
    for i in range(300):
        d = r.submit(order(i=f"q{i}", now=r.clock()))
        r.ex.cancel(d.client_id)
        r.pump()
        r.clock.advance(250)
    r.lane.heartbeat(r.clock())
    r.ledger.account(SYM, BID, r.clock())
    assert len(r.ledger.orders) <= 241                            # solo el último minuto


def test_t30_is_not_woken_by_another_lane_fill():
    class Svc:
        def __init__(self) -> None:
            self.synced = 0

        def active(self, symbol):
            return ["t"]

        def expected_qty(self, symbol):
            return 0.002

        def sync(self, tr):
            self.synced += 1
    svc = Svc()
    router = UserEventRouter(svc=svc, external=lambda _s: 0.001)
    router([UserEvent("account", 1, 1, SYM, position=0.003)])     # +0,001 del carril HFT
    assert svc.synced == 0
    router([UserEvent("account", 2, 2, SYM, position=0.001)])     # cambió la parte de T30
    assert svc.synced == 1
