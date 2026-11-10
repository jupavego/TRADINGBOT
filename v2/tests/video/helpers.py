"""Utilidades de las pruebas de T64: lista de prueba, transporte simulado y reloj."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from eim.data.video.catalog import VideoCatalog
from eim.data.video.discover import QuotaGuard, YouTubeApi
from eim.data.video.pipeline import quota_guard
from eim.video import watchlist as W

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "video"
CH = "UCtestAAAAAAAAAAAAAAAAAA"
NOW = int(datetime(2026, 11, 10, 12, tzinfo=UTC).timestamp() * 1000)


def fixture(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_watchlist(permission: str = "propio", **budget) -> W.Watchlist:
    base = W.load()
    ch = W.Channel(channel_id=CH, name="Canal de prueba", priority=4, languages=("es",),
                   permission=permission, verified=True)
    return base.model_copy(update={
        "channels": (ch,), "budget": base.budget.model_copy(update=budget)})


test_watchlist.__test__ = False   # no es una prueba


class FakeYouTube:
    """Responde como la Data API v3 con las respuestas de `tests/fixtures/video`."""

    def __init__(self, videos: dict | None = None) -> None:
        self.videos = videos or fixture("videos.json")
        self.calls: list[str] = []
        self.quota_after: int | None = None   # tras N llamadas, Google dice quotaExceeded
        self.fail_channel: set[str] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        ep = request.url.path.rsplit("/", 1)[-1]
        self.calls.append(ep)
        assert request.url.params.get("key") == "clave-de-prueba"
        if self.quota_after is not None and len(self.calls) > self.quota_after:
            return httpx.Response(403, json=fixture("quota_exceeded.json"))
        if ep == "channels":
            cid = request.url.params["id"]
            if cid in self.fail_channel:
                return httpx.Response(500, json={"error": {"errors": [{"reason": "backendError"}]}})
            if cid != CH:
                return httpx.Response(200, json={"items": []})
            return httpx.Response(200, json=fixture("channels.json"))
        if ep == "playlistItems":
            return httpx.Response(200, json=fixture("playlist_items.json"))
        if ep == "videos":
            ids = set(request.url.params["id"].split(","))
            return httpx.Response(200, json={"items": [
                v for v in self.videos["items"] if v["id"] in ids]})
        return httpx.Response(404)

    def api(self, quota: QuotaGuard) -> YouTubeApi:
        client = httpx.Client(transport=httpx.MockTransport(self.handler))
        return YouTubeApi("clave-de-prueba", quota, client, min_interval_s=0,
                          sleep=lambda s: None)


def api_for(cat: VideoCatalog, wl: W.Watchlist, fake: FakeYouTube, now: int = NOW) -> YouTubeApi:
    return fake.api(quota_guard(cat, wl, now))
