"""Job de descubrimiento (T40): muestra el WS oficial `trades` y registra candidatos."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from eim.core.leaders import Leader
from eim.data.leader_store import LeaderStore
from eim.data.providers.leaders import HyperliquidStream, now_ms
from eim.leaders import params as P
from eim.leaders.discovery import aggregate, rank


async def discover(store: LeaderStore, seconds: float, coins: tuple[str, ...] = P.DISCOVERY_COINS,
                   top: int = P.DISCOVERY_TOP, clock: Callable[[], int] = now_ms,
                   connect=None) -> list[Leader]:
    """Muestra el WS `trades` `seconds` segundos y registra candidatos nuevos en el almacén."""
    samples: dict = {}
    stop = asyncio.Event()
    kw = {"connect": connect} if connect is not None else {}
    stream = HyperliquidStream([{"type": "trades", "coin": c} for c in coins],
                               lambda m, _t: aggregate([m], samples), **kw)
    task = asyncio.create_task(stream.run(stop))
    await asyncio.sleep(seconds)
    stop.set()
    await task
    found = rank(samples, clock(), window_s=seconds, top=top)
    return [ld for ld in found if store.upsert_leader(ld, clock())]
