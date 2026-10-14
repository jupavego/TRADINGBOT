"""Tests de la capa de datos con HTTP simulado (sin red)."""

from __future__ import annotations

import httpx
import pytest

from eim.core import Candle
from eim.data import Store, build_snapshot, sync_candles, sync_derivatives
from eim.data.providers import BinanceFutures, ProviderError

H = 3_600_000
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H)
NOW = T0 + 10_000 * H
R0 = NOW - 10 * H  # dentro de la retención de OI


def _row(t: int) -> list:
    p = 100.0 + (t - T0) // H % 7
    return [t, str(p), str(p + 2), str(p - 1), str(p + 1), "10.5", t + H - 1]


def _make(handler, **kw) -> BinanceFutures:
    client = httpx.Client(
        base_url="https://fapi.binance.com", transport=httpx.MockTransport(handler)
    )
    return BinanceFutures(client, sleep=lambda s: None, clock=lambda: NOW, **kw)


def _klines_handler(missing: set[int] | None = None):
    missing = missing or set()

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/fapi/v1/klines"
        q = req.url.params
        lo, hi, lim = int(q["startTime"]), int(q["endTime"]), int(q["limit"])
        ts = [t for t in range(lo - lo % H + (H if lo % H else 0), hi + 1, H) if t not in missing]
        return httpx.Response(200, json=[_row(t) for t in ts[:lim]])

    return handler


def test_klines_paginate_and_drop_forming():
    prov = _make(_klines_handler())
    out = prov.klines("BTCUSDT", "1h", T0, NOW + 5 * H)  # incluye velas aún no cerradas
    assert out[0].t == T0 and len(out) == 10_000  # sin duplicados y sin la vela en formación
    assert all(b.t - a.t == H for a, b in zip(out, out[1:], strict=False))


def test_retries_then_succeeds_and_fails():
    calls = {"n": 0}

    def flaky(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json=[_row(T0)])

    assert len(_make(flaky).klines("BTCUSDT", "1h", T0, T0 + H)) == 1
    assert calls["n"] == 3
    with pytest.raises(ProviderError):
        _make(lambda r: httpx.Response(503), max_retries=2).klines("BTCUSDT", "1h", T0, T0 + H)
    with pytest.raises(ProviderError):  # 400 no se reintenta
        _make(lambda r: httpx.Response(400, json={"code": -1121})).klines("X", "1h", T0, T0 + H)


def test_funding_and_open_interest():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/fapi/v1/fundingRate":
            return httpx.Response(200, json=[
                {"symbol": "BTCUSDT", "fundingTime": T0 + 8 * H * i, "fundingRate": "0.0001"}
                for i in range(3)])
        assert req.url.path == "/futures/data/openInterestHist"
        return httpx.Response(200, json=[
            {"symbol": "BTCUSDT", "sumOpenInterest": "123.4", "timestamp": R0 + H * i}
            for i in range(4)])

    prov = _make(handler)
    assert prov.funding_rates("BTCUSDT", T0, T0 + 100 * H) == [
        (T0 + 8 * H * i, 0.0001) for i in range(3)]
    assert len(prov.open_interest("BTCUSDT", "1h", T0, NOW)) == 4  # recortado a 29 días


def test_store_upsert_read_gaps(tmp_path):
    store = Store(tmp_path)
    mk = lambda t, c: Candle(t=t, o=c, h=c + 1, l=c - 1, c=c, v=1.0)  # noqa: E731
    store.upsert_candles("BTCUSDT", "1h", [mk(T0 + i * H, 10) for i in (0, 1, 3, 4)], "test")
    assert store.find_gaps("BTCUSDT", "1h") == [(T0 + 2 * H, T0 + 2 * H)]
    n = store.upsert_candles("BTCUSDT", "1h", [mk(T0 + 3 * H, 99), mk(T0 + 2 * H, 50)], "test")
    assert n == 5 and store.find_gaps("BTCUSDT", "1h") == []
    got = store.read_candles("BTCUSDT", "1h")
    assert [c.t for c in got] == [T0 + i * H for i in range(5)] and got[3].c == 99
    assert [c.t for c in store.read_candles("BTCUSDT", "1h", last=2)] == [T0 + 3 * H, T0 + 4 * H]
    assert store.read_candles("ETHUSDT", "1h") == [] and store.source(
        "candles", "BTCUSDT", "1h") == "test"
    with pytest.raises(ValueError):
        store.upsert_candles("BTCUSDT", "5m", [], "x")


def test_sync_fills_incrementally_and_gaps(tmp_path):
    store = Store(tmp_path)
    missing = {T0 + 50 * H, T0 + 51 * H}
    prov = _make(_klines_handler(missing))
    r = sync_candles(store, prov, "BTCUSDT", "1h", T0, T0 + 100 * H)
    assert r == {"fetched": 98, "total": 98, "gaps": 1}
    prov2 = _make(_klines_handler())  # el hueco ahora existe en el servidor
    r = sync_candles(store, prov2, "BTCUSDT", "1h", T0, T0 + 120 * H)
    assert r["fetched"] == 22 and r["total"] == 120 and r["gaps"] == 0


def test_build_snapshot_coverage(tmp_path):
    store = Store(tmp_path)
    sync_candles(store, _make(_klines_handler()), "BTCUSDT", "1h", T0, T0 + 50 * H)
    rows = [(T0 + 8 * H, 0.0001), (T0 + 999 * H, 1.0)]
    store.upsert_series("funding", "BTCUSDT", "-", rows, "bf")
    snap = build_snapshot(store, "BTCUSDT", "1h", 20, asof=T0 + 50 * H)
    assert len(snap.candles) == 20 and snap.candles[-1].t == T0 + 49 * H
    assert snap.coverage["candles"] == (T0 + 30 * H, T0 + 49 * H)
    assert snap.sources["candles"] == "binance-futures"
    assert snap.funding is None and "funding" not in snap.coverage  # fuera de la ventana
    assert snap.open_interest is None
    # una vela aún no cerrada a `asof` no entra
    partial = build_snapshot(store, "BTCUSDT", "1h", 5, asof=T0 + 49 * H + 5)
    assert partial.candles[-1].t == T0 + 48 * H
    # menos datos que n: la cobertura es la real
    assert len(build_snapshot(store, "BTCUSDT", "1h", 500, asof=T0 + 50 * H).candles) == 50
    assert build_snapshot(store, "ETHUSDT", "1h", 5, asof=T0).coverage == {}


def test_sync_derivatives(tmp_path):
    def handler(req: httpx.Request) -> httpx.Response:
        if "fundingRate" in req.url.path:
            return httpx.Response(200, json=[{"fundingTime": T0, "fundingRate": "0.0002"}])
        if "LongShort" in req.url.path:
            return httpx.Response(200, json=[{"longShortRatio": "1.2", "timestamp": R0}])
        if "basis" in req.url.path:
            return httpx.Response(200, json=[{"basisRate": "0.001", "timestamp": R0}])
        return httpx.Response(200, json=[{"sumOpenInterest": "5", "timestamp": R0}])

    store = Store(tmp_path)
    assert sync_derivatives(store, _make(handler), "BTCUSDT", "1h", T0, NOW) == {
        "funding": 1, "open_interest": 1, "long_short_ratio": 1, "basis": 1}
    assert store.read_series("basis", "BTCUSDT", "1h") == [(R0, 0.001)]
    assert store.read_series("funding", "BTCUSDT") == [(T0, 0.0002)]


def test_build_snapshot_neighbor_timeframes(tmp_path):
    """T35: velas cerradas del marco inferior y superior, sin incluir velas aún abiertas."""
    store = Store(tmp_path)
    q, h4 = H // 4, 4 * H
    base = T0 - T0 % h4

    def cs(step: int, n: int) -> list[Candle]:
        return [Candle(t=base + k * step, o=1, h=2, l=0.5, c=1.5, v=1) for k in range(n)]

    store.upsert_candles("BTCUSDT", "1h", cs(H, 40), "s1h")
    store.upsert_candles("BTCUSDT", "15m", cs(q, 160), "s15m")
    store.upsert_candles("BTCUSDT", "4h", cs(h4, 10), "s4h")
    asof = base + 30 * H + 1  # 4h en curso: la de base+28h aún no cerró
    snap = build_snapshot(store, "BTCUSDT", "1h", 20, asof=asof)
    assert set(snap.candles_tf) == {"15m", "4h"}
    assert snap.candles_tf["15m"][-1].t == base + 30 * H - q
    assert snap.candles_tf["4h"][-1].t == base + 24 * H
    assert snap.sources["candles_4h"] == "s4h" and "candles_15m" in snap.coverage
    assert build_snapshot(store, "ETHUSDT", "1h", 5, asof=asof).candles_tf is None
