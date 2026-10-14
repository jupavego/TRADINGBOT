"""T32: la API solo atiende al equipo local (Host, cliente, origen de WebSocket, token)."""

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from eim.api.config import Settings
from eim.api.security import LocalOnlyMiddleware, _hostname, is_loopback
from tests.local_client import LocalClient

ORIGINS = ("http://127.0.0.1:5173",)


def _app(token: str | None = None) -> FastAPI:
    app = FastAPI()

    @app.get("/x")
    def x() -> dict:
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(w: WebSocket):
        await w.accept()
        await w.send_json({"ok": True})
        await w.close()

    app.add_middleware(LocalOnlyMiddleware, allowed_hosts=("127.0.0.1", "localhost", "::1"),
                       origins=ORIGINS, token=token)
    return app


def test_local_passes():
    with LocalClient(_app()) as c:
        assert c.get("/x").json() == {"ok": True}
        assert c.get("/x", headers={"host": "localhost:8000"}).status_code == 200
        assert c.get("/x", headers={"host": "[::1]:8000"}).status_code == 200


def test_foreign_host_rejected_dns_rebinding():
    with LocalClient(_app()) as c:
        r = c.get("/x", headers={"host": "evil.example:8000"})
    assert r.status_code == 400 and "host" in r.json()["detail"]


def test_remote_client_rejected_without_token():
    with LocalClient(_app(), client=("192.168.1.20", 4000)) as c:
        assert c.get("/x").status_code == 403


def test_remote_client_with_token():
    with LocalClient(_app("s3cr3t"), client=("192.168.1.20", 4000)) as c:
        assert c.get("/x", headers={"authorization": "Bearer s3cr3t"}).status_code == 200
        assert c.get("/x", headers={"authorization": "Bearer nope"}).status_code == 403
        assert c.get("/x").status_code == 403


def test_default_testclient_is_not_local():
    with TestClient(_app()) as c:            # Host "testserver", cliente "testclient"
        assert c.get("/x").status_code == 400


def test_websocket_origin():
    with LocalClient(_app()) as c:
        with c.websocket_connect("/ws", headers={"origin": ORIGINS[0]}) as w:
            assert w.receive_json() == {"ok": True}
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/ws", headers={"origin": "https://evil.example"}) as w:
                w.receive_json()


@pytest.mark.parametrize("raw,host", [("127.0.0.1:8000", "127.0.0.1"), ("LocalHost", "localhost"),
                                      ("[::1]:80", "::1"), ("::1", "::1")])
def test_hostname(raw, host):
    assert _hostname(raw) == host


def test_is_loopback():
    assert is_loopback("127.0.0.5") and is_loopback("::1")
    assert not is_loopback("10.0.0.1") and not is_loopback("testclient") and not is_loopback(None)


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("EIM_ALLOWED_HOSTS", "127.0.0.1, eim.lan")
    monkeypatch.setenv("EIM_API_TOKEN", "abc")
    s = Settings.from_env()
    assert s.allowed_hosts == ("127.0.0.1", "eim.lan") and s.api_token == "abc"
    assert "abc" not in repr(s)
    monkeypatch.delenv("EIM_ALLOWED_HOSTS")
    monkeypatch.delenv("EIM_API_TOKEN")
    s = Settings.from_env()
    assert s.allowed_hosts == ("127.0.0.1", "localhost", "::1") and s.api_token is None


# POST sin efecto lateral: procesa el archivo subido y responde (CORS impide leer la respuesta).
POST_WITHOUT_CONFIRM = {"/v2/more/bitacora"}


def test_every_mutating_post_requires_confirm_header(tmp_path):
    from eim.api.main import create_app
    paths = create_app(Settings(data_dir=tmp_path)).openapi()["paths"]
    posts = {p: ops["post"] for p, ops in paths.items() if "post" in ops}
    assert len(posts) >= 9
    missing = sorted(p for p, op in posts.items() if p not in POST_WITHOUT_CONFIRM
                     and not any(q["in"] == "header" and q["name"].lower() == "x-eim-confirm"
                                 for q in op.get("parameters", [])))
    assert missing == [], f"POST sin cabecera X-EIM-Confirm (CSRF): {missing}"
