"""T83 · Flujo de usuario por WebSocket (sin red): `listenKey`, reconexión y estado del carril."""

from __future__ import annotations

import asyncio
import json
from collections import deque

import pytest

from eim.execution.broker import BrokerError, OrderRejected
from eim.execution.user_stream_ws import ListenKeyKeeper, run_user_stream
from tests.hft.hft_helpers import Clock
from tests.hft.test_hft_execution import OTU


class Api:
    def __init__(self) -> None:
        self.keys = deque(["k1", "k2", "k3"])
        self.calls: list[str] = []
        self.fail: OrderRejected | None = None

    def listen_key(self) -> str:
        self.calls.append("POST")
        return self.keys.popleft()

    def keepalive_listen_key(self) -> None:
        self.calls.append("PUT")
        if self.fail is not None:
            raise self.fail


def test_listen_key_is_created_once_renewed_on_time_and_recreated_on_1125():
    clk, api = Clock(), Api()
    k = ListenKeyKeeper(api, clk, keepalive_ms=1_000)
    assert k.renew() is False and api.calls == []                # sin clave aún: nada
    assert k.key() == k.key() == "k1" and api.calls == ["POST"]
    assert k.renew() is False and api.calls == ["POST"]           # aún no toca
    clk.advance(1_000)
    assert k.renew() is False and api.calls == ["POST", "PUT"]
    clk.advance(1_000)
    api.fail = OrderRejected("This listenKey does not exist.", -1125)
    assert k.renew() is True and k.key() == "k2"
    clk.advance(1_000)
    api.fail = OrderRejected("otra cosa", -1000)
    with pytest.raises(OrderRejected):
        k.renew()


class Conn:
    def __init__(self, msgs: list) -> None:
        self.msgs = deque(msgs)

    async def __aenter__(self) -> Conn:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def recv(self) -> str:
        if self.msgs:
            m = self.msgs.popleft()
            if isinstance(m, Exception):
                raise m
            return m
        await asyncio.sleep(3_600)                               # inactivo
        return ""


def test_stream_reconnects_after_cuts_and_renews_an_expired_key():
    api = Api()
    keeper = ListenKeyKeeper(api, Clock())
    sessions = [Conn([json.dumps(OTU), ConnectionError("corte")]),
                Conn([json.dumps({"e": "listenKeyExpired", "E": 1, "listenKey": "k1"})]),
                Conn([json.dumps(OTU)])]
    urls: list[str] = []
    status: list[bool] = []
    events: list = []
    stop = asyncio.Event()

    def connect(url, **_kw):
        urls.append(url)
        return sessions.pop(0)

    def on_events(evs) -> None:
        events.extend(evs)
        if len([e for e in events if e.kind == "order"]) == 2:
            stop.set()

    asyncio.run(asyncio.wait_for(run_user_stream(
        keeper, on_events, status.append, stop, connect=connect, idle_s=0.05,
        backoff_s=0.01), timeout=5))
    base = "wss://fstream.binancefuture.com/ws/"
    assert urls == [base + "k1", base + "k1", base + "k2"]
    assert status == [True, False, True, False, True, False]     # cada corte bloquea el carril
    assert [e.kind for e in events] == ["order", "expired", "order"]
    assert events[0].state.client_id == "eih-abc"


def test_only_testnet_stream_hosts():
    with pytest.raises(BrokerError, match="host bloqueado"):
        asyncio.run(run_user_stream(ListenKeyKeeper(Api()), print, print, asyncio.Event(),
                                    base="wss://fstream.binance.com/private/ws/"))
