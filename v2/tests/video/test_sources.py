"""T64: lectura de respuestas, RSS seguro, clave nunca en errores, CLI y servicio sin fuente."""

import json

import httpx
import pytest

from eim.data.video.catalog import VideoCatalog
from eim.data.video.discover import QuotaGuard, SourceError, YouTubeApi
from eim.data.video.parse import iso_duration_s, video_from_api, videos_from_rss
from eim.data.video.pipeline import run_discover
from eim.data.video.service import serve
from eim.video.__main__ import main
from tests.video.helpers import CH, FIX, NOW, FakeYouTube, api_for, fixture, test_watchlist


@pytest.mark.parametrize(("text", "s"), [("PT25M10S", 1510), ("PT1H5M", 3900), ("P0D", None),
                                         ("P1DT1S", 86401), ("raro", None), (None, None)])
def test_iso_duration(text, s):
    assert iso_duration_s(text) == s


def test_api_items_parse_live_language_and_completed_streams():
    items = {i["id"]: video_from_api(i) for i in fixture("videos.json")["items"]}
    assert items["vidFED00003"].live == "upcoming" and items["vidFED00003"].duration_s is None
    assert items["vidOLD00006"].live == "completed" and items["vidOLD00006"].language == "es"
    assert items["vidETH00002"].language == "en-US"
    assert video_from_api({"id": "x"}) is None


def test_rss_parses_and_rejects_doctype():
    metas = videos_from_rss((FIX / "rss.xml").read_bytes(), CH)
    assert [m.video_id for m in metas] == ["vidBTC00001"]
    assert metas[0].duration_s is None and metas[0].source == "youtube_rss"
    bomb = b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaa">]><feed/>'
    with pytest.raises(ValueError):
        videos_from_rss(bomb, CH)


def test_errors_never_leak_the_key():
    def handler(request):
        return httpx.Response(400, json={"error": {"errors": [{"reason": "keyInvalid"}]}})
    api = YouTubeApi("SECRETO123", QuotaGuard(10, lambda: 0, lambda n: None),
                     httpx.Client(transport=httpx.MockTransport(handler)), min_interval_s=0,
                     sleep=lambda s: None)
    with pytest.raises(SourceError) as exc:
        api.channel(CH)
    assert "SECRETO123" not in str(exc.value) and "keyInvalid" in str(exc.value)


def test_rss_never_overwrites_api_metadata(tmp_path):
    cat = VideoCatalog(tmp_path / "v.duckdb")
    wl = test_watchlist()
    run_discover(cat, wl, NOW, api_for(cat, wl, FakeYouTube()), None)
    rss = videos_from_rss((FIX / "rss.xml").read_bytes(), CH)
    assert cat.record_videos(rss, NOW + 1, wl.version, wl.hash)["changed"] == 0
    cat.close()


def test_cli_list_and_show_explain_each_video(tmp_path, capsys):
    cat = VideoCatalog(tmp_path / "video.duckdb")
    wl = test_watchlist()
    run_discover(cat, wl, NOW, api_for(cat, wl, FakeYouTube()), None)
    cat.close()
    assert main(["--data-dir", str(tmp_path), "list", "--asof", "2026-11-10T12:00"]) == 0
    out = capsys.readouterr().out
    assert "6 videos conocidos" in out and "más corto que la duración mínima" in out
    assert "pendiente" in out and "tema 1.00" in out
    assert main(["--data-dir", str(tmp_path), "show", "vidCOOK0005"]) == 0
    assert "ningún tema de la lista" in capsys.readouterr().out
    assert main(["--data-dir", str(tmp_path), "coverage"]) == 0
    assert "consultas ok" in capsys.readouterr().out
    assert main(["--data-dir", str(tmp_path), "queue"]) == 0


def test_service_without_key_degrades_and_beats(tmp_path, monkeypatch):
    monkeypatch.delenv("EIM_YOUTUBE_API_KEY", raising=False)
    assert serve(tmp_path, test_watchlist(), every_s=60, once=True) == 1
    beat = json.loads((tmp_path / "video" / "heartbeat.json").read_text(encoding="utf-8"))
    assert beat["state"] == "sin_fuente" and "EIM_YOUTUBE_API_KEY" in beat["error"]
    assert beat["watchlist"] == "v1"
