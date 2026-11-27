"""T92: `SimBroker` con fichas de instrumento (sesión, multiplicador, lote, comisión de clase);
un símbolo sin ficha (BTC/ETH) da exactamente lo mismo que antes."""
from __future__ import annotations

import pytest

from eim.backtest.costs import EquityCostModel, FuturesCostModel
from eim.execution.broker import FILLED, LIMIT, MARKET, NEW, STOP, OrderSpec
from eim.execution.sim_broker import SimBroker
from eim.execution.sim_instrument import BrokerInstrument
from tests.backtest.t92_helpers import equity, future


def _btc_session(b: SimBroker) -> list:
    """Secuencia de T31: entrada a mercado, stop, límite que espera y cierre."""
    b.set_price("BTCUSDT", 60_000.0)
    b.post_order(OrderSpec(client_id="e", symbol="BTCUSDT", side=1, kind=MARKET, qty=0.25))
    b.post_order(OrderSpec(client_id="s", symbol="BTCUSDT", side=-1, kind=STOP, qty=None,
                           trigger=59_000.0, close_position=True))
    b.set_price("ETHUSDT", 3_000.0)
    b.post_order(OrderSpec(client_id="l", symbol="ETHUSDT", side=1, kind=LIMIT, qty=1.0,
                           price=2_900.0))
    b.set_price("ETHUSDT", 2_890.0)
    b.set_price("BTCUSDT", 60_500.0)
    b.set_price("BTCUSDT", 58_900.0)
    return [b.balance, b.equity(), b.position("BTCUSDT"), b.dump()]


def test_symbol_without_card_is_unchanged():
    plain = _btc_session(SimBroker(balance=10_000, maker_fee=0.0002))
    other = SimBroker(balance=10_000, maker_fee=0.0002,
                      instruments={"ACME": BrokerInstrument.from_instrument(equity())})
    assert _btc_session(other) == plain
    # cifras de antes de T92, a mano: tomador 4 pb (T31), creador 2 pb para la límite que esperó
    fees = 60_000 * 0.25 * 0.0004 + 58_900 * 0.25 * 0.0004 + 2_900 * 1.0 * 0.0002
    assert plain[0] == pytest.approx(10_000 - 275.0 - fees, abs=1e-9)
    assert other.round_qty("BTCUSDT", 0.12345) == SimBroker().round_qty("BTCUSDT", 0.12345)


def test_closed_market_order_waits_and_fills_at_open_price():
    closed = {1, 2}
    bi = BrokerInstrument.from_instrument(equity(), is_open=lambda t: t not in closed)
    b = SimBroker(balance=10_000, instruments={"ACME": bi})
    b.set_price("ACME", 50.0, t=1)                         # cerrado
    o = b.post_order(OrderSpec(client_id="a", symbol="ACME", side=1, kind=MARKET, qty=10.0))
    assert o.status == NEW and b.position("ACME").qty == 0
    b.set_price("ACME", 49.0, t=2)                         # sigue cerrado: nada se casa
    assert b.order_by_id("a").status == NEW
    b.set_price("ACME", 53.0, t=3)                         # apertura con hueco
    o = b.order_by_id("a")
    assert o.status == FILLED and o.avg_price == 53.0
    assert b.balance == pytest.approx(10_000 - EquityCostModel().commission(10, 53.0))


def test_future_multiplier_commission_and_whole_contracts():
    m = FuturesCostModel(commission_per_contract=2.0)
    b = SimBroker(balance=100_000, instruments={
        "CLX": BrokerInstrument.from_instrument(future(multiplier=1000), model=m)})
    assert b.round_qty("CLX", 2.7) == 2.0
    b.set_price("CLX", 70.0)
    b.post_order(OrderSpec(client_id="e", symbol="CLX", side=1, kind=MARKET, qty=2.0))
    b.set_price("CLX", 70.5)
    assert b.equity() == pytest.approx(100_000 - 4.0 + 0.5 * 1000 * 2)
    b.post_order(OrderSpec(client_id="x", symbol="CLX", side=-1, kind=MARKET, qty=2.0,
                           reduce_only=True))
    assert b.balance == pytest.approx(100_000 - 8.0 + 1_000.0)
    assert b.position("CLX").qty == 0
