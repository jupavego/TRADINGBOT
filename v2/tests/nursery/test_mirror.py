"""Espejo en vivo de la cantera (2026-11-20): un equipo publica, los demás leen. Sin red: el
«remoto» es un repo git vacío en una carpeta temporal."""

from __future__ import annotations

import subprocess

import pytest

from eim.nursery.mirror import BRANCH, MirrorGit, NurseryMirror, make_mirror, snapshot

PAYLOAD = {"mode": "SIMULADO", "enabled": True, "variant": "cantera", "label": "Cantera",
           "live": {"last_tick": 1, "error": "", "blocked": None},
           "prereg": {"version": "cantera_v1", "sha256": "x", "alta_ms": 0},
           "balance": {"windows": {}, "agents": []}, "panel": {"prospects": []},
           "accounts": [{"account": "a", "equity_curve": [1, 2, 3]}], "events": [{"e": 1}]}


class _Desk:
    def __init__(self) -> None:
        self.obj: dict | None = {"n": 1}

    def summary(self) -> dict | None:
        return self.obj


@pytest.fixture()
def remote(tmp_path):
    r = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", str(r)], check=True)
    return r


def test_snapshot_keeps_what_the_tab_paints_and_drops_the_heavy_parts():
    s = snapshot(PAYLOAD, "juanpablo-cpu", 123)
    assert s["balance"] == PAYLOAD["balance"] and s["panel"] == PAYLOAD["panel"]
    assert "accounts" not in s and "events" not in s and "enabled" not in s
    assert s["mirror"] == {"machine": "juanpablo-cpu", "published_ms": 123}


def test_publish_then_read_round_trip_keeps_a_single_photo(tmp_path, remote):
    desk = _Desk()
    pub = NurseryMirror("publish", MirrorGit(remote.as_uri(), tmp_path / "a"), "juanpablo-cpu",
                        desk=desk, payload=lambda: PAYLOAD, publish_s=900)
    pub.tick(now=1000.0)
    assert pub.error == "" and pub.last_ok_ms == 1_000_000
    rd = NurseryMirror("read", MirrorGit(remote.as_uri(), tmp_path / "b"), "portatil")
    rd.tick(now=1001.0)
    assert rd.error == "" and rd.latest["mirror"]["machine"] == "juanpablo-cpu"
    # sin cálculo nuevo no vuelve a publicar antes de la hora; con uno nuevo, tras 15 min
    pub.tick(now=1500.0)
    assert pub.last_ok_ms == 1_000_000
    desk.obj = {"n": 2}
    pub.tick(now=1000.0 + 901)
    assert pub.last_ok_ms == 1_901_000
    log = subprocess.run(["git", "--git-dir", str(remote), "rev-list", "--count", BRANCH],
                         capture_output=True, text=True, check=True)
    assert log.stdout.strip() == "1"            # una sola foto en el remoto: no crece


def test_failures_are_recorded_not_raised(tmp_path):
    rd = NurseryMirror("read", MirrorGit((tmp_path / "no-existe.git").as_uri(), tmp_path / "c"),
                       "portatil")
    rd.tick(now=5.0)
    assert rd.latest is None and rd.error


def test_role_follows_where_the_cantera_runs(tmp_path):
    env = {"EIM_MACHINE": "portatil"}
    assert make_mirror(False, tmp_path, env=env) is None
    assert make_mirror(True, tmp_path, env=env).role == "read"
    assert make_mirror(True, tmp_path, _Desk(), lambda: PAYLOAD, env=env).role == "publish"


def test_api_serves_the_mirror_when_the_cantera_is_off_here(tmp_path, remote):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from eim.api.nursery import OFF, build_nursery_router

    rd = NurseryMirror("read", MirrorGit(remote.as_uri(), tmp_path / "b"), "portatil")
    app = FastAPI()
    app.include_router(build_nursery_router(None, rd))
    c = TestClient(app)
    j = c.get("/v2/nursery").json()
    assert j["enabled"] is False and j["mirror"]["waiting"] and OFF["reason"] in j["reason"]
    rd.latest = snapshot(PAYLOAD, "juanpablo-cpu", 7)
    j = c.get("/v2/nursery").json()
    assert j["enabled"] is True and j["mirror"]["machine"] == "juanpablo-cpu"
    assert j["balance"] == PAYLOAD["balance"]
    assert c.get("/v2/nursery/prospect/x").status_code == 404
