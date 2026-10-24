"""Conexión del flujo de datos de usuario de la testnet (T83): `listenKey` + WebSocket.

- `ListenKeyKeeper`: crea el `listenKey` (`POST /fapi/v1/listenKey`), lo renueva cada 30 min
  (`PUT`; vale 60 min) y, si el exchange dice `-1125` (ya no existe), crea otro. Lo usa la
  conexión; las peticiones REST van por `BinanceWsApiBroker` (solo cabecera de la clave).
- `run_user_stream`: conexión con reintentos y espera exponencial. Cada mensaje → eventos
  normalizados (`parse_user_event`) → `on_events`. `on_status(False)` en cada corte: el carril
  bloquea y cancela (los fills de ese tramo no llegarían por evento) y, al reconectar, la
  reconciliación recupera lo perdido. `listenKeyExpired` → clave nueva y reconexión.

URL de testnet `wss://fstream.binancefuture.com/ws/<listenKey>` (sin verificar: la documentación
oficial no publica la de testnet y la de producción pasó a `/private/ws/`; se confirma con la
primera conexión con claves, BACKLOG T83). Solo hosts de testnet.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import urlsplit

from eim.execution.broker import BrokerError, OrderRejected
from eim.execution.user_stream import UserEvent, parse_user_event
from eim.observability import hooks_service

STREAM_URL = "wss://fstream.binancefuture.com/ws/"
STREAM_HOSTS = frozenset({"fstream.binancefuture.com"})
KEEPALIVE_MS = 30 * 60_000
COMPONENT = "execution.hft"


class ListenKeyApi(Protocol):
    def listen_key(self) -> str: ...

    def keepalive_listen_key(self) -> None: ...


class ListenKeyKeeper:
    def __init__(self, api: ListenKeyApi,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000),
                 keepalive_ms: int = KEEPALIVE_MS) -> None:
        self.api, self._clock, self.keepalive_ms = api, clock, keepalive_ms
        self._key: str | None = None
        self._at = 0

    def key(self) -> str:
        if self._key is None:
            self._key, self._at = self.api.listen_key(), self._clock()
        return self._key

    def expire(self) -> None:
        self._key = None

    def renew(self) -> bool:
        """Renueva si toca. True si la clave cambió (hay que reconectar)."""
        if self._key is None or self._clock() - self._at < self.keepalive_ms:
            return False
        try:
            self.api.keepalive_listen_key()
            self._at = self._clock()
            return False
        except OrderRejected as e:
            if e.code != -1125:
                raise
        self._key = None
        self.key()
        return True


def check_stream_host(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "wss" or parts.hostname not in STREAM_HOSTS:
        raise BrokerError(f"host bloqueado: '{parts.hostname}' no es el flujo de la testnet")


async def _nap(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass


async def run_user_stream(keeper: ListenKeyKeeper, on_events: Callable[[list[UserEvent]], None],
                          on_status: Callable[[bool], None], stop: asyncio.Event,
                          base: str = STREAM_URL, connect: Callable[..., Any] | None = None,
                          idle_s: float = 60.0, backoff_s: float = 1.0) -> None:
    check_stream_host(base)
    if connect is None:
        import websockets
        connect = websockets.connect
    backoff = backoff_s
    while not stop.is_set():
        try:
            key = await asyncio.to_thread(keeper.key)
            async with connect(base + key, ping_interval=20, open_timeout=15) as ws:
                on_status(True)
                backoff = backoff_s
                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=idle_s)
                    except TimeoutError:
                        raw = None
                    if raw is not None:
                        evs = parse_user_event(json.loads(raw))
                        on_events(evs)
                        if any(e.kind == "expired" for e in evs):
                            keeper.expire()
                            break
                    if await asyncio.to_thread(keeper.renew):
                        break                                 # clave nueva: reconectar
        except Exception as exc:  # corte de red, clave rechazada, mensaje ilegible…
            hooks_service.service_error(COMPONENT, exc, detail={"conn": "flujo de usuario"},
                                        min_interval_s=30)
        on_status(False)
        if stop.is_set():
            return
        await _nap(stop, backoff)
        backoff = min(backoff * 2, 60.0)
