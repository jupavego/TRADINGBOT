"""T83 · WS API de órdenes (testnet) y extras REST, sin red: firma, hosts, errores y 429/418."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections import deque

import pytest

from eim.execution.binance_rest import Credentials
from eim.execution.binance_ws_api import BinanceWsApiBroker, WsApiClient
from eim.execution.broker import (
    LIMIT,
    STOP,
    BrokerError,
    NetworkError,
    OrderRejected,
    OrderSpec,
    RateLimited,
)
from eim.execution.service import ensure_order
from eim.execution.sim_broker import SimBroker
from tests.execution.fake_binance import KEY, SECRET, FakeBinance, _order_json
from tests.hft.hft_helpers import Clock

SYM = "BTCUSDT"


class FakeWsApi:
    """Conexión síncrona falsa del WS API: comprueba la firma y casa contra un `SimBroker`."""

    def __init__(self, sim: SimBroker) -> None:
        self.sim, self.sent, self.urls = sim, [], []
        self.out: deque[str] = deque()
        self.forced: list[tuple[int, dict]] = []
        self.silent = 0                                # respuestas que no llegan (tiempo agotado)
        self.closed = False

    def __call__(self, url: str) -> FakeWsApi:          # fábrica de conexiones
        self.urls.append(url)
        self.closed = False
        return self

    def send(self, text: str) -> None:
        msg = json.loads(text)
        self.sent.append(text)
        if self.silent:
            self.silent -= 1
            return
        self.out.append(json.dumps({"id": "de-otra-peticion", "status": 200, "result": {}}))
        self.out.append(json.dumps({"id": msg["id"], **self._handle(msg)}))

    def recv(self, timeout: float | None = None) -> str:
        if not self.out:
            raise TimeoutError("sin respuesta")
        return self.out.popleft()

    def close(self) -> None:
        self.closed = True

    def _handle(self, msg: dict) -> dict:
        if self.forced:
            status, err = self.forced.pop(0)
            return {"status": status, "error": err}
        p = dict(msg["params"])
        sig = p.pop("signature")
        payload = "&".join(f"{k}={p[k]}" for k in sorted(p))
        if p.get("apiKey") != KEY or sig != hmac.new(SECRET.encode(), payload.encode(),
                                                     hashlib.sha256).hexdigest():
            return {"status": 400, "error": {"code": -1022, "msg": "Signature not valid."}}
        try:
            if msg["method"] == "order.place":
                o = self.sim.post_order(OrderSpec(
                    p["newClientOrderId"], p["symbol"], 1 if p["side"] == "BUY" else -1,
                    p["type"], qty=float(p["quantity"]), price=float(p.get("price") or 0) or None,
                    reduce_only=p.get("reduceOnly") == "true", tif=p.get("timeInForce", "GTC")))
            else:
                o = self.sim.order_by_id(p["origClientOrderId"])
                if o is None:
                    return {"status": 400, "error": {"code": -2013, "msg": "Order does not exist."}}
                if msg["method"] == "order.cancel":
                    self.sim.cancel(p["symbol"], o.client_id, False)
                    o = self.sim.order_by_id(o.client_id)
        except OrderRejected as e:
            return {"status": 400, "error": {"code": e.code, "msg": str(e)}}
        return {"status": 200, "result": _order_json(o),
                "rateLimits": [{"rateLimitType": "ORDERS", "interval": "SECOND",
                                "intervalNum": 10, "limit": 300, "count": 1}]}


def _broker(clk: Clock | None = None):
    clk = clk or Clock()
    fx = FakeBinance(SimBroker(min_notional=50.0))
    fx.sim.set_price(SYM, 100_000.05)
    ws = FakeWsApi(fx.sim)
    b = BinanceWsApiBroker(Credentials(KEY, SECRET), client=fx.client(), ws_connect=ws,
                           clock=clk)
    return b, fx, ws, clk


def test_orders_go_by_ws_api_signed_and_never_carry_the_secret():
    b, fx, ws, _ = _broker()
    st = b.post_order(OrderSpec("eih-1", SYM, 1, LIMIT, qty=0.001, price=100_000.0, tif="GTX"))
    assert st.status == "NEW" and st.client_id == "eih-1"
    sent = json.loads(ws.sent[-1])
    assert sent["method"] == "order.place" and sent["params"]["timeInForce"] == "GTX"
    assert {"apiKey", "timestamp", "recvWindow", "signature"} <= set(sent["params"])
    assert all(SECRET not in s for s in ws.sent + fx.raw)
    assert fx.posts("/fapi/v1/order") == []                       # nada por REST
    assert b.get_order(SYM, "eih-1", False).status == "NEW"
    b.cancel(SYM, "eih-1", False)
    b.cancel(SYM, "eih-1", False)                                 # idempotente
    assert b.get_order(SYM, "eih-1", False).status == "CANCELED"
    assert b.get_order(SYM, "no-existe", False) is None
    assert b.ws.rate_limits[0]["limit"] == 300


def test_conditional_orders_stay_on_rest():
    b, fx, ws, _ = _broker()
    b.post_order(OrderSpec("eih-2", SYM, 1, LIMIT, qty=0.001, price=100_000.2, tif="GTC"))
    n = len(ws.sent)
    b.post_order(OrderSpec("eim-x-s", SYM, -1, STOP, trigger=99_000.0, close_position=True))
    assert len(ws.sent) == n and len(fx.posts("/fapi/v1/algoOrder")) == 1


@pytest.mark.parametrize("url", ["wss://ws-fapi.binance.com/ws-fapi/v1",
                                 "ws://testnet.binancefuture.com/ws-fapi/v1",
                                 "https://testnet.binancefuture.com/ws-fapi/v1"])
def test_only_the_testnet_ws_api_host_is_allowed(url):
    with pytest.raises(BrokerError, match="host bloqueado"):
        WsApiClient(Credentials(KEY, SECRET), url=url)


@pytest.mark.parametrize("status, err, exc, attr", [
    (400, {"code": -5022, "msg": "Post Only order will be rejected"}, OrderRejected, -5022),
    (400, {"code": -4116, "msg": "ClientOrderId is duplicated."}, OrderRejected, True),
    (400, {"code": -1021, "msg": "Timestamp outside recvWindow"}, NetworkError, None),
    (503, {"code": -1001, "msg": "Unknown error"}, NetworkError, None),
])
def test_ws_api_errors_map_to_the_broker_contract(status, err, exc, attr):
    b, _, ws, _ = _broker()
    ws.forced.append((status, err))
    with pytest.raises(exc) as info:
        b.post_order(OrderSpec("eih-3", SYM, 1, LIMIT, qty=0.001, price=100_000.0, tif="GTX"))
    if attr is True:
        assert info.value.duplicate
    elif attr is not None:
        assert info.value.code == attr


def test_a_lost_answer_is_unknown_and_the_next_call_reconnects():
    b, _, ws, _ = _broker()
    ws.silent = 1
    with pytest.raises(NetworkError):
        b.get_order(SYM, "eih-4", False)
    assert ws.closed and len(ws.urls) == 1
    assert b.get_order(SYM, "eih-4", False) is None and len(ws.urls) == 2


def test_ws_api_429_waits_locally_until_retry_after():
    b, _, ws, clk = _broker()
    retry = clk() + b._rest.offset() + 2_000                      # hora del exchange
    ws.forced.append((429, {"code": -1003, "msg": "Too many requests",
                            "data": {"retryAfter": retry}}))
    with pytest.raises(RateLimited) as info:
        b.post_order(OrderSpec("eih-5", SYM, 1, LIMIT, qty=0.001, price=100_000.0, tif="GTX"))
    assert info.value.status == 429 and info.value.until == clk() + 2_000
    n = len(ws.sent)
    with pytest.raises(RateLimited):
        b.get_order(SYM, "eih-5", False)
    assert len(ws.sent) == n                                      # nada salió en la espera
    clk.advance(2_001)
    assert b.get_order(SYM, "eih-5", False) is None and len(ws.sent) == n + 1


@pytest.mark.parametrize("status, banned", [("429", False), ("418", True)])
def test_rest_rate_limit_waits_retry_after_and_sends_nothing_meanwhile(status, banned):
    b, fx, _, clk = _broker()
    b.equity()
    fx.fault("GET", "/fapi/v2/account", status)
    with pytest.raises(RateLimited) as info:
        b.equity()
    assert info.value.banned is banned and info.value.until == clk() + 2_000
    n = len(fx.raw)
    with pytest.raises(RateLimited):
        b.position(SYM)                                           # cualquier ruta espera
    assert len(fx.raw) == n
    clk.advance(2_001)
    assert b.equity() > 0


def test_rate_limit_is_never_queried_or_resent_by_ensure_order():
    class Limited(SimBroker):
        queries = 0

        def post_order(self, spec):
            raise RateLimited("HTTP 429", 429, 10)

        def get_order(self, symbol, client_id, conditional):
            Limited.queries += 1
            return None
    with pytest.raises(RateLimited):
        ensure_order(Limited(), OrderSpec("eih-6", SYM, 1, LIMIT, qty=0.001, price=1.0),
                     sleep=lambda _s: None)
    assert Limited.queries == 0


def test_countdown_and_listen_key_use_rest_with_the_right_security():
    b, fx, _, _ = _broker()
    b.countdown_cancel_all(SYM, 15_000)
    assert fx.countdowns == [(SYM, 15_000)] and "signature=" in fx.raw[-1]
    assert b.listen_key() == "lk-1"
    assert fx.headers[-1].get("x-mbx-apikey") == KEY and "signature" not in fx.raw[-1]
    b.keepalive_listen_key()
    b.close_listen_key()
    assert [m for m, pa, _ in fx.log if pa == "/fapi/v1/listenKey"] == ["POST", "PUT", "DELETE"]


def test_a_ws_api_ban_also_stops_rest_from_the_same_ip():
    b, fx, ws, clk = _broker()
    b.equity()
    ws.forced.append((418, {"code": -1003, "msg": "banned"}))
    with pytest.raises(RateLimited):
        b.get_order(SYM, "eih-7", False)
    n = len(fx.raw)
    with pytest.raises(RateLimited):
        b.countdown_cancel_all(SYM, 15_000)                       # el REST también espera
    assert len(fx.raw) == n and fx.countdowns == []
