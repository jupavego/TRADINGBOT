"""Ejecuciones de órdenes TWAP en el vigilante de líderes (T128, entregable 2).

Medido el 2026-11-02: dos líderes ejecutaban TWAP sin parar (278 y 597 porciones en una hora)
y `userFills` no las trae, así que su libro nunca cuadraba y se resincronizaba cada 30–60 s."""

from __future__ import annotations

import asyncio

import httpx

from eim.data.leader_store import LeaderStore
from eim.data.leader_watch import LeaderWatch
from eim.data.providers.leaders import HyperliquidInfo
from eim.leaders.parse import twap_fills
from tests.leaders.helpers import TEST, FakeInfo, fill, leader, state

NOW = 1_792_097_100_000


def _slice(f: dict, twap_id: int = 7) -> dict:
    return {"fill": f, "twapId": twap_id}


def _watch(tmp_path, info):
    store = LeaderStore.at_root(tmp_path)
    return LeaderWatch(store, info, [leader(TEST)], clock=lambda: NOW), store


def test_twap_slices_keep_the_book_without_resync(tmp_path):
    """La posición baja de 10 a 9 por dos porciones TWAP que `userFills` no trae."""
    s1 = fill("ZEC", "A", "0.4", "50", "10.0", NOW - 4000, 101, twapId=None)
    s2 = fill("ZEC", "A", "0.6", "50", "9.6", NOW - 2000, 102, twapId=None)
    info = FakeInfo([state(NOW - 5000, ("ZEC", "10.0", "50", 3, "cross")),
                     state(NOW - 1000, ("ZEC", "9.0", "50", 3, "cross"))], twap=[s1, s2])
    w, store = _watch(tmp_path, info)
    asyncio.run(w.bootstrap(TEST))
    rec = asyncio.run(w.reconcile(TEST))
    assert rec.match and TEST not in w.suspect
    assert store.query("SELECT resynced FROM leader_recon") == [(False,)]
    assert store.query("SELECT count(*) FROM leader_gaps")[0][0] == 0
    assert store.query("SELECT tid FROM leader_fills ORDER BY t") == [(101,), (102,)]


def test_ws_twap_channel_is_ingested_like_user_fills(tmp_path):
    info = FakeInfo([state(NOW - 5000, ("ZEC", "10.0", "50", 3, "cross")),
                     state(NOW - 1000, ("ZEC", "9.0", "50", 3, "cross"))])
    w, store = _watch(tmp_path, info)
    asyncio.run(w.bootstrap(TEST))
    w.on_message({"channel": "userTwapSliceFills", "data": {"user": TEST, "twapSliceFills": [
        _slice(fill("ZEC", "A", "1.0", "50", "10.0", NOW - 3000, 201))]}}, NOW)
    assert store.query("SELECT tid, channel FROM leader_fills") == [(201, "ws")]
    rec = asyncio.run(w.reconcile(TEST))                # el libro ya la aplicó: cuadra
    assert rec.match and store.query("SELECT resynced FROM leader_recon") == [(False,)]


def test_rest_twap_by_time_unwraps_and_pages():
    seen = []
    page = [_slice({"time": 1000 + i, "tid": i, "coin": "ZEC"}) for i in range(3)]

    def handler(req: httpx.Request) -> httpx.Response:
        body = req.read().decode()
        seen.append(body)
        return httpx.Response(200, json=page)

    info = HyperliquidInfo(httpx.Client(transport=httpx.MockTransport(handler)))
    out = info.user_twap_fills_by_time(TEST, 1000)
    assert [r["tid"] for r in out] == [0, 1, 2]
    assert '"userTwapSliceFillsByTime"' in seen[0]
    assert twap_fills([{"twapId": 1}, None, _slice({"tid": 5})]) == [{"tid": 5}]
