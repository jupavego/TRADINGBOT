"""Broker spot de testnet (T45): seguridad, claves, órdenes, comisiones y saldos."""

import httpx
import pytest

from eim.execution.binance_rest import ENV_KEY as FUT_KEY
from eim.execution.binance_rest import ENV_SECRET as FUT_SECRET
from eim.execution.binance_rest import Credentials
from eim.execution.binance_spot_testnet import ENV_KEY, ENV_SECRET, BinanceSpotTestnetBroker
from eim.execution.broker import LIMIT, MARKET, STOP, BrokerError, OrderRejected, OrderSpec
from tests.execution.fake_binance import KEY, SECRET
from tests.execution.fake_venue import FakeHTTP, Venue

SYM = "BTCUSDT"


def _broker(**venue):
    v = Venue({SYM: 100_000.0}, step=0.00001, tick=0.01, **venue)
    h = FakeHTTP(v)
    return v, h, BinanceSpotTestnetBroker(Credentials(KEY, SECRET), client=h.client())


@pytest.mark.parametrize("url", ["https://api.binance.com", "http://testnet.binance.vision",
                                 "https://testnet.binance.vision.evil.io"])
def test_non_testnet_host_blocked(url):
    with pytest.raises(BrokerError, match="bloqueado"):
        BinanceSpotTestnetBroker(Credentials(KEY, SECRET), base_url=url)


def test_injected_client_with_real_host_blocked():
    with pytest.raises(BrokerError, match="bloqueado"):
        BinanceSpotTestnetBroker(Credentials(KEY, SECRET),
                                 client=httpx.Client(base_url="https://api.binance.com"))


def test_keys_from_spot_env_then_futures_env(monkeypatch):
    for k in (ENV_KEY, ENV_SECRET, FUT_KEY, FUT_SECRET):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(BrokerError, match=FUT_KEY):
        BinanceSpotTestnetBroker()
    monkeypatch.setenv(FUT_KEY, KEY)
    monkeypatch.setenv(FUT_SECRET, SECRET)                   # cuenta demo: misma clave
    b = BinanceSpotTestnetBroker(client=FakeHTTP(Venue({SYM: 1.0})).client())
    assert b.equity() == 50_000.0 and SECRET not in repr(b)
    monkeypatch.setenv(ENV_KEY, "otra")
    with pytest.raises(BrokerError, match=ENV_SECRET):
        BinanceSpotTestnetBroker()


def test_bad_signature_rejected():
    _, h, _ = _broker()
    b = BinanceSpotTestnetBroker(Credentials(KEY, "otro"), client=h.client())
    with pytest.raises(OrderRejected, match="Signature"):
        b.balances()


def test_buy_with_fee_in_base_reports_fills_and_trades():
    v, h, b = _broker(fee_rate=0.001, fee_in_base=True)
    st = b.post_order(OrderSpec("eia-x-a1", SYM, 1, LIMIT, qty=0.01, price=100_100.0))
    assert st.filled == pytest.approx(0.01) and st.avg_price == pytest.approx(100_010.0)
    assert st.fee == pytest.approx(0.00001) and st.fee_asset == "BTC"
    again = b.get_order(SYM, "eia-x-a1")                     # sin `fills`: los lee de myTrades
    assert again.fee == pytest.approx(0.00001) and again.fee_asset == "BTC"
    assert b.position(SYM).qty == pytest.approx(1.00999)
    assert h.posts("/api/v3/order")[0]["newOrderRespType"] == "FULL"


def test_limit_rests_then_cancel_and_unknown_order():
    v, _, b = _broker()
    st = b.post_order(OrderSpec("eia-x-a2", SYM, 1, LIMIT, qty=0.01, price=90_000.0))
    assert st.is_open and [o.client_id for o in b.open_orders(SYM)] == ["eia-x-a2"]
    b.cancel(SYM, "eia-x-a2")
    b.cancel(SYM, "eia-x-a2")                                # idempotente
    assert b.get_order(SYM, "eia-x-a2").status == "CANCELED"
    assert b.get_order(SYM, "nada") is None


def test_rounding_minimums_and_rejections():
    _, _, b = _broker()
    assert b.round_qty(SYM, 0.0123456) == pytest.approx(0.01234)
    assert b.round_qty(SYM, 0.000001) == 0.0
    assert b.round_price(SYM, 100_000.005) == pytest.approx(100_000.01)
    assert b.min_notional(SYM) == 5.0 and b.base_asset(SYM) == "BTC"
    with pytest.raises(BrokerError, match="desconocido"):
        b.round_qty("XXXUSDT", 1.0)
    with pytest.raises(BrokerError, match="no admite"):
        b.post_order(OrderSpec("eia-x-s", SYM, -1, STOP, qty=0.01, trigger=90_000.0))
    with pytest.raises(OrderRejected, match="insufficient"):
        b.post_order(OrderSpec("eia-x-m", SYM, -1, MARKET, qty=5.0))


def test_book_and_empty_book():
    v, _, b = _broker()
    bid, ask = b.book_top(SYM)
    assert bid < 100_000.0 < ask
    v.empty.add(SYM)
    assert b.book_top(SYM) is None and b.depth(SYM) == ([], [])
