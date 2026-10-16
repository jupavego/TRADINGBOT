"""Hyperliquid por API pública oficial (sin claves): `/info` por REST y WS (T40, fuente T33).

- `HyperliquidInfo`: estado de cuenta (`clearinghouseState`), ejecuciones (`userFills`,
  `userFillsByTime` paginado), funding (`userFunding` paginado), `vaultDetails` y
  `portfolio` (T41), con
  reintentos y presupuesto de peso por minuto (límite oficial 1200/IP). Estima además el
  desfase del reloj local frente al del servidor (`time` de `clearinghouseState` contra el
  punto medio del viaje): sin corregirlo la latencia medida sale negativa.
- `HyperliquidStream`: una conexión WS con suscripciones, latido (`ping`) y reconexión con
  espera exponencial; avisa del corte (`on_down`) y de la vuelta (`on_up`) para que el
  vigilante registre el hueco y lo rellene por REST.
Binance no tiene fuente automatizada (T33: solo registro manual).
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from eim.data.providers.binance import ProviderError
from eim.leaders.params import (
    BACKOFF_MAX_S,
    FILLS_PAGE,
    FUNDING_PAGE,
    MAX_PAGES,
    PING_EVERY_S,
    REST_WEIGHT_PER_MIN,
)

INFO_URL = "https://api.hyperliquid.xyz/info"
WS_URL = "wss://api.hyperliquid.xyz/ws"
_RETRY_STATUS = {429, 500, 502, 503, 504}
_LIGHT = {"clearinghouseState": 2, "l2Book": 2, "allMids": 2}  # el resto pesa 20
log = logging.getLogger(__name__)


def now_ms() -> int:
    return int(time.time() * 1000)


class HyperliquidInfo:
    """Cliente REST de `/info` (POST JSON)."""

    def __init__(self, client: httpx.Client | None = None, *, url: str = INFO_URL,
                 max_retries: int = 4, backoff: float = 1.0,
                 weight_per_min: int = REST_WEIGHT_PER_MIN,
                 sleep: Callable[[float], None] = time.sleep,
                 monotonic: Callable[[], float] = time.monotonic,
                 wall: Callable[[], int] = now_ms) -> None:
        self._client = client or httpx.Client(timeout=15.0)
        self._url = url
        self._max_retries, self._backoff = max_retries, backoff
        self._budget = weight_per_min
        self._sleep, self._mono = sleep, monotonic
        self._spent: deque[tuple[float, int]] = deque()  # (instante, peso) del último minuto
        self._wall = wall
        self._offsets: deque[int] = deque(maxlen=21)
        self.last_rtt: tuple[int, int] | None = None  # reloj local antes/después del POST
        self.calls = 0

    def clock_offset_ms(self) -> int:
        """Mediana de (hora del servidor − reloj local); 0 hasta la primera medición."""
        return int(statistics.median(self._offsets)) if self._offsets else 0

    def _throttle(self, weight: int) -> None:
        while True:
            now = self._mono()
            while self._spent and now - self._spent[0][0] >= 60.0:
                self._spent.popleft()
            if sum(w for _, w in self._spent) + weight <= self._budget or not self._spent:
                self._spent.append((now, weight))
                return
            self._sleep(60.0 - (now - self._spent[0][0]) + 0.05)

    def post(self, body: dict[str, Any]) -> Any:
        """POST con reintentos (429/5xx/red) y presupuesto de peso."""
        self._throttle(_LIGHT.get(body.get("type", ""), 20))
        last = ""
        for attempt in range(self._max_retries + 1):
            self.calls += 1
            try:
                a = self._wall()
                resp = self._client.post(self._url, json=body)
                self.last_rtt = (a, self._wall())
            except httpx.TransportError as exc:
                last = f"red: {exc}"
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) >= 20:  # peso extra por elementos
                        self._spent.append((self._mono(), len(data) // 20))
                    return data
                last = f"HTTP {resp.status_code}: {resp.text[:200]}"
                if resp.status_code not in _RETRY_STATUS:
                    raise ProviderError(f"hyperliquid {body.get('type')} {last}")
            if attempt < self._max_retries:
                self._sleep(self._backoff * 2**attempt)
        raise ProviderError(f"hyperliquid {body.get('type')} agotó reintentos ({last})")

    def clearinghouse_state(self, user: str) -> dict:
        data = self.post({"type": "clearinghouseState", "user": user})
        if isinstance(data, dict) and data.get("time") and self.last_rtt:
            a, b = self.last_rtt  # solo el viaje del POST que respondió (sin esperas ni reintentos)
            if b - a < 2_000:
                self._offsets.append(int(data["time"]) - (a + b) // 2)
        return data

    def user_fills(self, user: str) -> list[dict]:
        """Las últimas 2000 ejecuciones (de la más nueva a la más vieja)."""
        return self.post({"type": "userFills", "user": user})

    def _paged(self, body: dict, start: int, end: int | None, page: int) -> list[dict]:
        """Pagina por `startTime` hasta una página corta o `MAX_PAGES` (lo más antiguo)."""
        out: list[dict] = []
        for _ in range(MAX_PAGES):
            q = body | {"startTime": start} | ({"endTime": end} if end is not None else {})
            rows = self.post(q)
            out += rows
            if len(rows) < page:
                return out
            nxt = max(int(r["time"]) for r in rows)
            if nxt <= start:
                break
            start = nxt  # el borde se repite: la deduplicación lo absorbe
        log.warning("%s truncado en %d filas desde %s: faltan las más recientes",
                    body.get("type"), len(out), start)
        return out

    def user_fills_by_time(self, user: str, start: int, end: int | None = None) -> list[dict]:
        """Ejecuciones con t ≥ start (solo las 10 000 más recientes son consultables)."""
        return self._paged({"type": "userFillsByTime", "user": user, "aggregateByTime": False},
                           start, end, FILLS_PAGE)

    def user_funding(self, user: str, start: int, end: int | None = None) -> list[dict]:
        return self._paged({"type": "userFunding", "user": user}, start, end, FUNDING_PAGE)

    def vault_details(self, vault: str) -> dict:
        return self.post({"type": "vaultDetails", "vaultAddress": vault})

    def portfolio(self, user: str) -> list:
        """Valor de cuenta y PnL acumulado por periodo (`day` … `perpAllTime`), T41."""
        return self.post({"type": "portfolio", "user": user})


def _default_connect(url: str):
    import websockets

    return websockets.connect(url, open_timeout=15, ping_interval=20, max_size=2**24)


class HyperliquidStream:
    """Conexión WS con reconexión. `on_message(msg, observed_at)` recibe todo salvo `pong` y
    confirmaciones de suscripción."""

    def __init__(self, subscriptions: list[dict], on_message: Callable[[dict, int], None], *,
                 on_down: Callable[[int, str], None] | None = None,
                 on_up: Callable[[int], None] | None = None, url: str = WS_URL,
                 connect: Callable[[str], Any] = _default_connect,
                 clock: Callable[[], int] = now_ms, ping_every: float = PING_EVERY_S,
                 backoff_max: float = BACKOFF_MAX_S, recv_timeout: float = 1.0,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self.subscriptions = subscriptions
        self.on_message, self.on_down, self.on_up = on_message, on_down, on_up
        self.url, self._connect, self._clock = url, connect, clock
        self.ping_every, self.backoff_max, self._sleep = ping_every, backoff_max, sleep
        self.recv_timeout = recv_timeout
        self.connects = 0
        self.down_since: int | None = None
        self.last_msg: int | None = None

    async def run(self, stop: asyncio.Event) -> None:
        backoff = 1.0
        while not stop.is_set():
            try:
                async with self._connect(self.url) as ws:
                    for sub in self.subscriptions:
                        await ws.send(json.dumps({"method": "subscribe", "subscription": sub}))
                    self.connects += 1
                    backoff = 1.0
                    if self.down_since is not None:
                        since, self.down_since = self.down_since, None
                        if self.on_up:
                            self.on_up(since)
                    await self._pump(ws, stop)
                    if stop.is_set():
                        return
                    raise ConnectionError("el servidor cerró la conexión")
            except Exception as exc:  # corte de red, cierre, 429… → hueco y reintento
                if stop.is_set():
                    return
                if self.down_since is None:
                    self.down_since = self.last_msg or self._clock()
                    if self.on_down:
                        self.on_down(self.down_since, f"{type(exc).__name__}: {exc}"[:200])
                await self._sleep(backoff)
                backoff = min(backoff * 2, self.backoff_max)

    async def _pump(self, ws: Any, stop: asyncio.Event) -> None:
        last_ping = last_rx = time.monotonic()
        while not stop.is_set():
            now = time.monotonic()
            if now - last_ping >= self.ping_every:
                await ws.send(json.dumps({"method": "ping"}))
                last_ping = now
            if now - last_rx > 3 * self.ping_every:
                raise ConnectionError("sin tráfico: el latido no obtuvo respuesta")
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=self.recv_timeout)
            except TimeoutError:
                continue
            last_rx = time.monotonic()
            observed = self._clock()
            self.last_msg = observed
            msg = json.loads(raw)
            if msg.get("channel") in ("pong", "subscriptionResponse"):
                continue
            self.on_message(msg, observed)
