"""Superficie de la API (T32): solo local por defecto.

- `Host` fuera de `allowed_hosts` → 400. Frena el *DNS rebinding*: una web maliciosa que hace
  resolver su dominio a 127.0.0.1 llega con su propio `Host` y queda fuera (CORS no protege aquí).
- Cliente que no es de bucle local (127.0.0.0/8, ::1) → 403, salvo que exista `EIM_API_TOKEN` y
  la petición traiga `Authorization: Bearer <token>`. Sin token configurado no hay acceso remoto.
- WebSocket con `Origin` que no está en `cors_origins` → se cierra (CORS no cubre WebSocket).

Middleware ASGI puro: cubre HTTP y WebSocket por igual.
"""

from __future__ import annotations

import hmac
import ipaddress
import json

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def _hostname(host: str) -> str:
    host = host.strip().lower()
    if host.startswith("["):                       # [::1]:8000
        return host[1:host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def is_loopback(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def _headers(scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


def token_ok(headers: dict[str, str], token: str | None) -> bool:
    if not token:
        return False
    auth = headers.get("authorization", "")
    given = auth[7:] if auth.lower().startswith("bearer ") else ""
    return hmac.compare_digest(given.encode(), token.encode())


def check(scope, allowed_hosts, origins, token: str | None) -> tuple[int, str] | None:
    """Devuelve (código, motivo) si la petición se rechaza; None si pasa."""
    h = _headers(scope)
    if _hostname(h.get("host", "")) not in allowed_hosts:
        return 400, "host no permitido (API solo local; ver EIM_ALLOWED_HOSTS)"
    client = scope.get("client")
    if not is_loopback(client[0] if client else None) and not token_ok(h, token):
        return 403, "acceso remoto denegado (API solo local; ver EIM_API_TOKEN)"
    if scope["type"] == "websocket" and h.get("origin") and h["origin"] not in origins:
        return 403, "origen de WebSocket no permitido"
    return None


class LocalOnlyMiddleware:
    def __init__(self, app, allowed_hosts, origins, token: str | None = None) -> None:
        self.app = app
        self.allowed_hosts = frozenset(_hostname(x) for x in allowed_hosts)
        self.origins = frozenset(origins)
        self.token = token or None

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        bad = check(scope, self.allowed_hosts, self.origins, self.token)
        if bad is None:
            return await self.app(scope, receive, send)
        code, reason = bad
        if scope["type"] == "websocket":
            await receive()                                   # websocket.connect
            await send({"type": "websocket.close", "code": 1008, "reason": reason})
            return
        body = json.dumps({"detail": reason}).encode()
        await send({"type": "http.response.start", "status": code,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
