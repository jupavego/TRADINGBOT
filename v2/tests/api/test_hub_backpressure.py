"""T123: el difusor no espera al análisis y lo que se descarta se cuenta.

Con un análisis que tarda (bloqueado a mano) y 10 cierres más mientras tanto: los ticks siguen
llegando a la pantalla, cada vela se guarda, se analiza solo la más reciente y los 9 cierres
intermedios quedan contados en `api.cierres`. Una pantalla que no lee pierde lo más viejo y se
cuenta en `api.clientes`, sin frenar a nadie.
"""

from __future__ import annotations

import asyncio

from eim.api.live import Hub
from eim.api.sources import LiveEvent
from eim.core import Candle
from eim.observability import queues

STEP = 60_000


def _c(i: int) -> Candle:
    return Candle(t=i * STEP, o=100, h=101, l=99, c=100.5, v=1)


class Src:
    name = "falsa"

    def __init__(self) -> None:
        self.events: asyncio.Queue = asyncio.Queue(1_000)

    async def stream(self, symbol: str, timeframe: str):
        while True:
            yield await self.events.get()


class Store:
    def __init__(self) -> None:
        self.saved: list[int] = []

    def upsert_candles(self, symbol, timeframe, candles, source) -> None:
        self.saved += [c.t for c in candles]


def _hub(src: Src, store: Store) -> Hub:
    hub = Hub(src, store, reports=None, registry=None)  # type: ignore[arg-type]
    hub._closes = queues.Gauge(queues.BY_ID["api.cierres"])
    hub._clients = queues.Gauge(queues.BY_ID["api.clientes"])

    async def no_boot(ch) -> None:
        return None
    hub._bootstrap = no_boot  # type: ignore[method-assign]
    return hub


def test_ticks_flow_while_analysis_runs_and_only_the_latest_close_is_analyzed():
    async def go():
        src, store = Src(), Store()
        hub = _hub(src, store)
        started, release, analyzed = asyncio.Event(), asyncio.Event(), []

        async def slow(ch, candle, persist_candle=True):
            analyzed.append(candle.t // STEP)
            started.set()
            await release.wait()
        hub._on_close = slow  # type: ignore[method-assign]
        ch, q = hub.subscribe("BTCUSDT", "1m")
        await src.events.put(LiveEvent(type="tick", candle=_c(0), closed=True))
        await asyncio.wait_for(started.wait(), 5)
        for i in range(1, 11):
            await src.events.put(LiveEvent(type="tick", candle=_c(i), closed=True))
        for _ in range(100):
            await src.events.put(LiveEvent(type="tick", candle=_c(11), closed=False))
        for _ in range(500):                         # el análisis de la vela 0 sigue bloqueado
            if q.qsize() >= 111:
                break
            await asyncio.sleep(0.01)
        during = (q.qsize(), list(analyzed), list(store.saved))
        release.set()
        for _ in range(500):
            if len(analyzed) == 2:
                break
            await asyncio.sleep(0.01)
        await hub.close()
        return during, analyzed, hub._closes

    (ticks, analyzed_then, saved_then), analyzed, g = asyncio.run(go())
    assert ticks == 111 and analyzed_then == [0]            # la pantalla no esperó al análisis
    assert saved_then == [i * STEP for i in range(11)]      # cada vela cerrada se guardó
    assert analyzed == [0, 10]                              # gana la más reciente
    assert g.dropped == 9 and "se analiza la" in g.last_cause


def test_a_slow_screen_loses_the_oldest_and_it_is_counted():
    async def go():
        hub = _hub(Src(), Store())
        ch, q = hub.subscribe("BTCUSDT", "1m")
        for i in range(300):
            hub._broadcast(ch, {"type": "n", "i": i})
        first = q.get_nowait()
        await hub.close()
        return q.maxsize, first, hub._clients
    size, first, g = asyncio.run(go())
    assert size == queues.capacity("api.clientes") == 256
    assert first["i"] == 300 - 256 and g.dropped == 300 - 256 and g.max_occupancy == 256
