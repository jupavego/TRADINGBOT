"""Proveedor Hyperliquid (T40) sin red: reintentos, paginación, peso, desfase de reloj y WS
con latido y reconexión."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from eim.data.providers.binance import ProviderError
from eim.data.providers.leaders import HyperliquidInfo, HyperliquidStream
from tests.leaders.helpers import FakeWS, fake_connect, load, no_sleep


def _info(handler, **kw) -> tuple[HyperliquidInfo, list[float]]:
    slept: list[float] = []
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HyperliquidInfo(client, sleep=slept.append, **kw), slept


def test_retries_then_succeeds_and_raises_on_client_error():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if json.loads(req.content)["type"] == "bad":
            return httpx.Response(422, text="Failed to deserialize")
        return httpx.Response(429) if calls["n"] < 3 else httpx.Response(200, json={"ok": 1})

    info, slept = _info(handler)
    assert info.post({"type": "clearinghouseState", "user": "0x"}) == {"ok": 1}
    assert slept == [1.0, 2.0]
    with pytest.raises(ProviderError):
        info.post({"type": "bad"})


def test_fills_by_time_paginates_until_short_page():
    fills = load("active_fills_by_time")
    pages = [[dict(fills[0], tid=i, time=1000 + i) for i in range(2000)], fills[:3]]
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append(body["startTime"])
        return httpx.Response(200, json=pages[len(seen) - 1])

    info, _ = _info(handler, weight_per_min=10_000)
    out = info.user_fills_by_time("0xabc", 1000)
    assert len(out) == 2003 and seen == [1000, 2999]


def test_weight_budget_throttles():
    clock = {"t": 0.0}
    info, slept = _info(lambda r: httpx.Response(200, json={}), weight_per_min=40,
                        monotonic=lambda: clock["t"])
    info.post({"type": "userFills", "user": "0x"})  # 20
    info.post({"type": "userFills", "user": "0x"})  # 40
    clock["t"] = 10.0
    info._sleep = lambda s: (slept.append(s), clock.__setitem__("t", clock["t"] + s))
    info.post({"type": "userFills", "user": "0x"})
    assert slept and slept[0] == pytest.approx(50.05)


def test_clock_offset_from_server_time():
    wall = iter([1000, 1200, 5000, 5100])
    info, _ = _info(lambda r: httpx.Response(200, json={"time": 2300, "assetPositions": []}),
                    wall=lambda: next(wall))
    assert info.clock_offset_ms() == 0
    info.clearinghouse_state("0x")  # 2300 − 1100
    info.clearinghouse_state("0x")  # 2300 − 5050
    assert info.clock_offset_ms() == (1200 + (2300 - 5050)) // 2


def _run(stream: HyperliquidStream, stop: asyncio.Event, timeout: float = 5.0) -> None:
    async def go():
        await asyncio.wait_for(stream.run(stop), timeout)
    asyncio.run(go())


def test_stream_filters_control_messages_and_reconnects_with_resubscribe():
    got, downs, ups = [], [], []
    msg = {"channel": "userFills", "data": {"user": "0xa", "fills": []}}
    c1 = FakeWS([{"channel": "subscriptionResponse", "data": {}}, msg,
                 ConnectionError("corte")])
    c2 = FakeWS([{"channel": "pong"}, msg])
    stop = asyncio.Event()
    subs = [{"type": "userFills", "user": "0xa"}, {"type": "userFills", "user": "0xb"}]

    def on_msg(m, t):
        got.append((m["channel"], t))
        if len(got) == 2:
            stop.set()

    clock = iter(range(100, 10_000, 10))
    stream = HyperliquidStream(subs, on_msg, on_down=lambda s, r: downs.append((s, r)),
                               on_up=ups.append, connect=fake_connect([c1, c2]),
                               clock=lambda: next(clock), sleep=no_sleep, recv_timeout=0.01)
    _run(stream, stop)
    assert [g[0] for g in got] == ["userFills", "userFills"]
    assert stream.connects == 2 and len(downs) == 1 and "corte" in downs[0][1]
    assert ups == [downs[0][0]]  # vuelta: hueco desde el último mensaje recibido
    for ws in (c1, c2):
        assert [m["subscription"] for m in ws.sent if m["method"] == "subscribe"] == subs


def test_stream_pings_and_drops_silent_connection():
    c1, c2 = FakeWS([]), FakeWS([{"channel": "trades", "data": []}])
    stop = asyncio.Event()
    downs = []
    stream = HyperliquidStream([{"type": "trades", "coin": "BTC"}],
                               lambda m, t: stop.set(), on_down=lambda s, r: downs.append(r),
                               connect=fake_connect([c1, c2]), ping_every=0.02,
                               recv_timeout=0.01, sleep=no_sleep)
    _run(stream, stop)
    assert any(m == {"method": "ping"} for m in c1.sent)
    assert downs and "latido" in downs[0]
