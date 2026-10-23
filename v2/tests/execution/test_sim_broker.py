"""`SimBroker`: reglas de casación que imitan a Binance y servicio en modo SIMULADO."""

import pytest

from eim.core import Mode
from eim.execution.broker import (
    EXPIRED,
    FILLED,
    LIMIT,
    MARKET,
    STOP,
    TAKE_PROFIT,
    TRIGGERED,
    OrderRejected,
    OrderSpec,
)
from eim.execution.gateway import OrderGateway
from eim.execution.service import CLOSED, OPEN, ExecutionService
from eim.execution.sim_broker import SimBroker
from tests.risk.helpers import NOW, account, decide, engine, market, plan

S = "BTCUSDT"


def sim(**kw) -> SimBroker:
    b = SimBroker(**kw)
    b.set_price(S, 100.0)
    return b


def test_market_limit_and_position():
    b = sim()
    assert b.post_order(OrderSpec("a", S, 1, MARKET, qty=1.0)).status == FILLED
    lim = b.post_order(OrderSpec("b", S, 1, LIMIT, qty=1.0, price=95.0))
    assert lim.is_open
    b.set_price(S, 94.0)
    assert b.order_by_id("b").status == FILLED and b.position(S).qty == 2.0
    assert b.position(S).entry_price == pytest.approx(97.5)


def test_exchange_rules():
    b = sim()
    b.post_order(OrderSpec("x", S, -1, STOP, trigger=90.0, close_position=True))
    with pytest.raises(OrderRejected) as e:
        b.post_order(OrderSpec("x", S, -1, STOP, trigger=90.0, close_position=True))
    assert e.value.duplicate
    with pytest.raises(OrderRejected, match="ReduceOnly"):
        b.post_order(OrderSpec("r", S, -1, MARKET, qty=1.0, reduce_only=True))
    with pytest.raises(OrderRejected, match="immediately"):
        b.post_order(OrderSpec("t", S, -1, STOP, trigger=101.0, close_position=True))
    with pytest.raises(OrderRejected, match="paso"):
        b.post_order(OrderSpec("q", S, 1, MARKET, qty=0.0005))
    b.set_price(S, 89.0)                                # sin posición: close_position expira
    assert b.order_by_id("x").status == EXPIRED


def test_stop_and_take_profit_close_position():
    b = sim()
    b.post_order(OrderSpec("e", S, 1, MARKET, qty=2.0))
    b.post_order(OrderSpec("tp", S, -1, TAKE_PROFIT, trigger=110.0, close_position=True))
    b.set_price(S, 111.0)
    assert b.order_by_id("tp").status == TRIGGERED and b.position(S).qty == 0
    assert b.balance > 10_000                           # ganancia menos comisiones


def test_service_in_simulated_mode():
    b = SimBroker()
    b.set_price(S, 100_000.0)
    eng, _, ks = engine()
    svc = ExecutionService(b, ks, sleep=lambda _: None, clock=lambda: NOW)
    d = decide(eng, plan(), account(), market(last_price=100_000.0))
    tr = svc.trades[OrderGateway(eng, svc).submit(d, NOW)]
    assert svc.mode == Mode.SIMULADO and tr.status == OPEN and b.position(S).qty == 0.025
    b.set_price(S, 104_000.0)
    svc.sync(tr)
    assert tr.status == CLOSED and tr.exit_reason == "TP" and b.open_orders(S) == []
