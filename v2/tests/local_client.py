"""Cliente de pruebas que llega como un navegador local (la API rechaza Host/cliente ajenos)."""

from fastapi.testclient import TestClient


class LocalClient(TestClient):
    def __init__(self, app, **kw) -> None:
        kw.setdefault("base_url", "http://127.0.0.1:8000")
        kw.setdefault("client", ("127.0.0.1", 50000))
        super().__init__(app, **kw)

    def websocket_connect(self, url, subprotocols=None, **kw):
        # Starlette arma el WebSocket contra `ws://testserver` sin importar `base_url`.
        headers = {"host": "127.0.0.1:8000", **(kw.pop("headers", None) or {})}
        return super().websocket_connect(url, subprotocols, headers=headers, **kw)
