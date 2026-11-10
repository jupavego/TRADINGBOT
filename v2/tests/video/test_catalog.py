"""T64: catálogo point-in-time sin duplicados, borrados y ediciones como filas nuevas, cola con
tope diario y degradación ante cuota agotada. Sin red (transporte simulado)."""

import copy

import pytest

from eim.data.video.catalog import VideoCatalog
from eim.data.video.pipeline import run_discover
from eim.video.models import VideoMeta
from tests.video.helpers import CH, NOW, FakeYouTube, api_for, test_watchlist

H = 3_600_000
ALL = {"vidBTC00001", "vidETH00002", "vidFED00003", "vidSHORT004", "vidCOOK0005", "vidOLD00006"}


@pytest.fixture
def cat(tmp_path):
    c = VideoCatalog(tmp_path / "video.duckdb")
    yield c
    c.close()


def _rows(cat):
    return cat._q("SELECT count(*) FROM videos")[0][0]


def test_repeat_discovery_adds_no_duplicates(cat):
    wl, fake = test_watchlist(), FakeYouTube()
    first = run_discover(cat, wl, NOW, api_for(cat, wl, fake), None)
    assert first["channels"][0]["added"] == 6 and _rows(cat) == 6
    second = run_discover(cat, wl, NOW + H, api_for(cat, wl, fake, NOW + H), None)
    assert second["channels"][0]["added"] == 0 and second["channels"][0]["unchanged"] == 6
    assert _rows(cat) == 6
    assert {r["video_id"] for r in cat.queue_rows()} == ALL
    assert "search" not in fake.calls          # 100 unidades por llamada: nunca se usa


def test_queue_states_and_reasons(cat):
    wl = test_watchlist()
    run_discover(cat, wl, NOW, api_for(cat, wl, FakeYouTube()), None)
    q = {r["video_id"]: r for r in cat.queue_rows()}
    assert {v for v, r in q.items() if r["state"] == "pendiente"} == {
        "vidBTC00001", "vidETH00002", "vidOLD00006"}
    assert set(q["vidFED00003"]["reasons"]) == {"en_vivo", "sin_duracion"}
    assert q["vidSHORT004"]["reasons"] == ["corto"]
    assert q["vidCOOK0005"]["reasons"] == ["sin_tema"]   # «BTCX» no es «btc»
    for r in q.values():
        assert r["state"] == "pendiente" or r["reasons"], "descarte sin motivo"
        assert {"tema", "actualidad", "prioridad", "filtros"} <= set(r["breakdown"])
        assert r["wl_version"] == "v1" and r["wl_hash"] == wl.hash


def test_queue_respects_daily_cap_and_permission(cat):
    wl = test_watchlist(compute_hours_per_day=0.2)       # 720 s
    run_discover(cat, wl, NOW, api_for(cat, wl, FakeYouTube()), None)
    q = {r["video_id"]: r for r in cat.queue_rows()}
    assert [v for v, r in q.items() if r["state"] == "pendiente"] == ["vidBTC00001"]
    assert q["vidETH00002"]["reasons"] == ["tope_diario"]
    assert cat.used_compute_s("2026-11-10") <= 720
    # sin permiso de transcripción nada entra a la cola (postura T62)
    wl2 = test_watchlist(permission="ninguno")
    c2 = VideoCatalog(":memory:")
    run_discover(c2, wl2, NOW, api_for(c2, wl2, FakeYouTube()), None)
    assert all(r["state"] == "descartado" and "sin_permiso" in r["reasons"]
               for r in c2.queue_rows())


def test_title_edit_deletion_and_republication_are_new_rows(cat):
    wl, fake = test_watchlist(), FakeYouTube()
    run_discover(cat, wl, NOW, api_for(cat, wl, fake), None)
    edited = copy.deepcopy(fake.videos)
    edited["items"] = [v for v in edited["items"] if v["id"] != "vidETH00002"]
    edited["items"][0]["snippet"]["title"] = "Bitcoin tras la Fed (corregido)"
    res = run_discover(cat, wl, NOW + H, api_for(cat, wl, FakeYouTube(edited), NOW + H), None)
    assert res["deleted"] == 1
    btc = cat.versions("vidBTC00001")
    assert [v["title"] for v in btc] == ["Bitcoin: ¿qué viene tras la reunión de la Fed?",
                                         "Bitcoin tras la Fed (corregido)"]
    eth = cat.versions("vidETH00002")
    assert [v["deleted"] for v in eth] == [False, True]
    assert cat.queue_get("vidETH00002")["reasons"] == ["borrado"]
    assert "vidETH00002" not in {v["video_id"] for v in cat.videos_asof(NOW + H)}
    assert "vidETH00002" in {v["video_id"] for v in cat.videos_asof(NOW)}   # lo que se sabía
    run_discover(cat, wl, NOW + 2 * H, api_for(cat, wl, FakeYouTube(), NOW + 2 * H), None)
    eth = cat.versions("vidETH00002")
    assert [v["deleted"] for v in eth] == [False, True, False]
    assert cat.queue_get("vidETH00002")["state"] == "pendiente"
    latest = {v["video_id"]: v for v in cat.videos_asof(NOW + 2 * H)}
    assert latest["vidETH00002"]["first_seen_at"] == NOW     # no cambia


def test_no_lookahead(cat):
    wl = test_watchlist()
    future = VideoMeta(video_id="vidFUTURE07", channel_id=CH, title="Bitcoin mañana",
                       published_at=NOW + 5 * H, duration_s=900, source="youtube_api")
    run_discover(cat, wl, NOW, api_for(cat, wl, FakeYouTube()), None)
    cat.record_videos([future], NOW, wl.version, wl.hash)
    assert cat.videos_asof(NOW - 1) == []                     # antes de first_seen_at
    assert "vidFUTURE07" not in {v["video_id"] for v in cat.videos_asof(NOW)}
    assert "vidFUTURE07" in {v["video_id"] for v in cat.videos_asof(NOW + 5 * H)}
    assert cat.queue_get("vidFUTURE07") is None


def test_google_quota_exceeded_degrades_without_crashing(cat):
    wl = test_watchlist()
    other = wl.channels[0].model_copy(update={"channel_id": "UCotherAAAAAAAAAAAAAAAAA"})
    wl2 = wl.model_copy(update={"channels": (*wl.channels, other)})
    fake = FakeYouTube()
    fake.quota_after = 2
    res = run_discover(cat, wl2, NOW, api_for(cat, wl2, fake), None)
    assert [c["ok"] for c in res["channels"]] == [False, False]
    assert all("cuota agotada" in c["error"] for c in res["channels"])
    assert len(fake.calls) == 3                          # tras agotarse no se llama más
    assert cat.coverage()[0]["fetch_failed"] == 1


def test_own_quota_budget_is_enforced(cat):
    wl = test_watchlist(quota_units_per_day=2)
    fake = FakeYouTube()
    res = run_discover(cat, wl, NOW, api_for(cat, wl, fake), None)
    assert not res["channels"][0]["ok"] and "presupuesto diario" in res["channels"][0]["error"]
    assert len(fake.calls) == 2 and cat.quota_used("2026-11-10") == 2


def test_one_failing_channel_does_not_stop_the_rest(cat):
    wl = test_watchlist()
    bad = wl.channels[0].model_copy(update={"channel_id": "UCbadBBBBBBBBBBBBBBBBBBB"})
    wl2 = wl.model_copy(update={"channels": (bad, wl.channels[0])})
    fake = FakeYouTube()
    fake.fail_channel = {"UCbadBBBBBBBBBBBBBBBBBBB"}
    res = run_discover(cat, wl2, NOW, api_for(cat, wl2, fake), None)
    assert res["channels"][0]["ok"] is False and "HTTP 500" in res["channels"][0]["error"]
    assert fake.calls[:3] == ["channels"] * 3            # reintentos
    assert res["channels"][1]["ok"] and res["channels"][1]["added"] == 6


def test_backfill_is_catalog_only_and_respects_since(cat):
    wl = test_watchlist()
    since = NOW - 5 * 24 * H                             # 2026-11-05
    res = run_discover(cat, wl, NOW, api_for(cat, wl, FakeYouTube()), None, channels=[CH],
                       since_ms=since, kind="backfill", mode="historico")
    ids = {v["video_id"] for v in cat.videos_asof(NOW)}
    assert "vidOLD00006" not in ids and len(ids) == 5
    assert res["kind"] == "backfill"
    assert {r["mode"] for r in cat.queue_rows()} == {"historico"}
    assert cat.coverage()[0]["backfill_since"] == since
