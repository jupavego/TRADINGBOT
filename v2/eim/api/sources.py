"""Fuentes de ticks en vivo: protocolo + WebSocket de klines de Binance con reconexión."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Protocol

from eim.core import Candle
from eim.observability import hooks_service


class LiveEvent(dict):
    """Evento: {type:tick, candle, closed} o {type:status, state, detail}."""


class LiveSource(Protocol):
    name: str

    def stream(self, symbol: str, timeframe: str) -> AsyncIterator[LiveEvent]:
        """Emite ticks de la vela en formación; `closed=True` en el último de cada vela.

        Si la conexión cae emite `status` ("down"/"up") y reconecta sola.
        """
        ...


def parse_kline(msg: dict) -> tuple[Candle, bool] | None:
    """Mensaje `kline` de Binance → (vela, cerrada). None si no es un kline."""
    k = msg.get("k")
    if not k:
        return None
    c = Candle(t=int(k["t"]), o=float(k["o"]), h=float(k["h"]), l=float(k["l"]),
               c=float(k["c"]), v=float(k["v"]),
               taker_buy_v=float(k["V"]) if "V" in k else None,
               trades=int(k["n"]) if "n" in k else None)
    return c, bool(k["x"])


class BinanceKlineSource:
    """`<symbol>@kline_<tf>` con reconexión exponencial y estado de la fuente."""

    name = "binance-futures-ws"

    def __init__(self, base_url: str, max_backoff: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._max_backoff = max_backoff

    async def stream(self, symbol: str, timeframe: str) -> AsyncIterator[LiveEvent]:
        import websockets

        url = f"{self._base}/{symbol.lower()}@kline_{timeframe}"
        backoff, was_down = 1.0, False
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, open_timeout=10) as ws:
                    backoff = 1.0
                    yield LiveEvent(type="status", state="up", detail="conectado")
                    if was_down:
                        hooks_service.service_event("data.live_ticks", "conexión restablecida",
                                                    detail={"symbol": symbol, "tf": timeframe})
                    was_down = False
                    async for raw in ws:
                        parsed = parse_kline(json.loads(raw))
                        if parsed:
                            hooks_service.beat("data.live_ticks", min_interval_s=60,
                                               detail={"symbol": symbol, "tf": timeframe})
                            yield LiveEvent(type="tick", candle=parsed[0], closed=parsed[1])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not was_down:
                    hooks_service.service_error("data.live_ticks", exc,
                                                detail={"symbol": symbol, "tf": timeframe})
                    yield LiveEvent(type="status", state="down",
                                    detail=f"{type(exc).__name__}: {exc}")
                    was_down = True
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self._max_backoff)
