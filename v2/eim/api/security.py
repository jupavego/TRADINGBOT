"""Superficie de la API (T32): solo local por defecto.

- `Host` fuera de `allowed_hosts` → 400. Frena el *DNS rebinding*: una web maliciosa que hace
  resolver su dominio a 127.0.0.1 llega con su propio `Host` y queda fuera (CORS no protege aquí).
- Cliente que no es de bucle local (127.0.0.0/8, ::1) → 403, salvo que exista `EIM_API_TOKEN` y
  la petición traiga `Authorization: Bearer <token>`. Un navegador no puede poner cabeceras en
  un WebSocket: ahí el token va como subprotocolo `eim-token.<token>` (la API lo devuelve al
  aceptar, como exige el protocolo). Sin token configurado no hay acceso remoto.
- WebSocket con `Origin` que no está en `cors_origins` → se cierra (CORS no cubre WebSocket).
- Cuerpo de petición mayor que `MAX_BODY_BYTES` → 413, antes de que el servidor lo reciba entero
  (por `Content-Length` y, si no viene, contando lo recibido).

Middleware ASGI puro: cubre HTTP y WebSocket por igual.
"""

from __future__ import annotations

import hmac
import ipaddress
import json

from fastapi import HTTPException

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
WS_TOKEN_PREFIX = "eim-token."
# Dos exports de la bitácora (`/v2/more/bitacora`: operaciones + ingresos, pocos MB cada uno)
# con margen; ningún otro endpoint recibe cuerpos grandes.
MAX_BODY_BYTES = 41 * 2**20


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


def _same(given: str, token: str) -> bool:
    return hmac.compare_digest(given.encode(), token.encode())


def ws_token_subprotocol(headers: dict[str, str]) -> str | None:
    """Subprotocolo `eim-token.…` ofrecido en el saludo del WebSocket (o None)."""
    offered = [p.strip() for p in headers.get("sec-websocket-protocol", "").split(",")]
    return next((p for p in offered if p.startswith(WS_TOKEN_PREFIX)), None)


def token_ok(headers: dict[str, str], token: str | None) -> bool:
    if not token:
        return False
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and _same(auth[7:], token):
        return True
    sub = ws_token_subprotocol(headers)
    return sub is not None and _same(sub[len(WS_TOKEN_PREFIX):], token)


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


async def _reject(send, code: int, reason: str) -> None:
    body = json.dumps({"detail": reason}).encode()
    await send({"type": "http.response.start", "status": code,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


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
        await _reject(send, code, reason)


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = _headers(scope).get("content-length", "")
        if length.isdigit() and int(length) > self.max_bytes:
            return await _reject(send, 413, self._reason())
        seen = 0

        async def limited():
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > self.max_bytes:            # cuerpo por trozos sin Content-Length
                    raise HTTPException(413, self._reason())
            return msg

        await self.app(scope, limited, send)

    def _reason(self) -> str:
        return f"cuerpo de la petición mayor a {self.max_bytes // 2**20} MB"
