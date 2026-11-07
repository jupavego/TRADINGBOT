"""T123: prueba de carga de la captura HFT — un productor 10× más rápido que su consumidor.

Se usan `reader` y `consumer` reales de `hft_ws` con un WebSocket falso que entrega 640 mensajes
por vuelta del bucle mientras el consumidor procesa 64 (el suyo es ceder cada 64). La memoria se
mide con `tracemalloc` (bytes reservados por Python, no una estimación) y se contrasta con la
misma carga sobre una cola sin tope, que sí crece. Los contadores deben cuadrar exactos con lo
que de verdad llegó al consumidor.
"""

from __future__ import annotations

import asyncio
import threading
import time
import tracemalloc
from collections import Counter

from eim.data.collectors import hft_ws
from eim.data.collectors.hft_writer import HftStore
from eim.observability import queues

N, PER_TURN = 100_000, 640          # 640 por vuelta frente a los 64 del consumidor: 10×


class Clock:
    def now(self) -> tuple[int, int]:
        return time.time_ns(), time.monotonic_ns()


class FloodWS:
    def __init__(self, total: int, stop: asyncio.Event) -> None:
        self.total, self.stop = total, stop

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for i in range(self.total):
            if i % PER_TURN == 0:
                await asyncio.sleep(0)
            yield f'{{"e":"x","i":{i}}}'
        if self.total == 0:          # conexión de después: tranquila hasta que se pare
            await self.stop.wait()


class Connect:
    def __init__(self, stop: asyncio.Event) -> None:
        self.calls, self.stop = 0, stop

    def __call__(self, url: str, **kw) -> FloodWS:
        self.calls += 1
        return FloodWS(N if self.calls == 1 else 0, self.stop)


class Cap:
    """Consumidor falso: cuenta lo que le llega, sin parsear."""

    def __init__(self, store=None) -> None:
        self.kinds: Counter[str] = Counter()
        self.marked = 0
        self.counts: Counter[str] = Counter()
        self.store = store

    def handle(self, item: tuple) -> None:
        self.kinds[item[0]] += 1
        if item[0] == "overflow":
            self.marked += item[2]
        elif self.store is not None:
            self.store.add("bbo", 0, (1, 2, 3, 4))


class NoStore:
    backlog = pending_rows = 0

    def maybe_flush(self) -> None:
        pass

    def pending(self) -> int:
        return 0


async def _flood(maxsize: int) -> dict:
    stop = asyncio.Event()
    inbox = hft_ws.Inbox(maxsize, gauge=queues.Gauge(queues.BY_ID["hft.recepcion"]))
    conn, cap = Connect(stop), Cap()
    tasks = [asyncio.create_task(hft_ws.reader("market", "ws://x", inbox, Clock(), stop,
                                               connect=conn)),
             asyncio.create_task(hft_ws.consumer(inbox, cap, NoStore(), stop))]
    tracemalloc.start()
    samples = []
    try:
        while conn.calls < 2:                       # mientras dura la ráfaga
            samples.append(tracemalloc.get_traced_memory()[0])
            await asyncio.sleep(0)
        for _ in range(500):                        # se vacía y entran las marcas pendientes
            if cap.kinds["open"] >= 2 and inbox.q.empty():
                break
            await asyncio.sleep(0.01)
    finally:
        tracemalloc.stop()
    alive = all(not t.done() for t in tasks)
    # foto antes de parar: al parar, la recepción ofrece otro cierre
    got = {"kinds": Counter(cap.kinds), "marked": cap.marked, "dropped": inbox.dropped,
           "gauge": inbox.gauge.dropped, "gauge_max": inbox.gauge.max_occupancy,
           "errors": cap.counts["errores_proceso"]}
    stop.set()
    await asyncio.wait_for(asyncio.gather(*tasks), 10)
    q = len(samples) // 4
    return {**got, "alive": alive, "max_seen": inbox.max_seen,
            "early": max(samples[q:2 * q]), "late": max(samples[3 * q:])}


def test_flood_10x_memory_flat_and_drops_counted_exactly(monkeypatch):
    monkeypatch.setattr(hft_ws, "RECONNECT_S", 0.01)
    r = asyncio.run(_flood(2_000))
    k = r["kinds"]
    assert r["alive"], "con la ráfaga se cerró una etapa"
    assert r["max_seen"] <= 2_000
    assert k["msg"] <= 0.2 * N, "el productor no fue 10× más rápido"
    # exactos: cada oferta llega al consumidor o se cuenta como descartada, y las marcas cuadran
    offered = N + 2 + 1                             # mensajes + dos aperturas + un cierre
    assert k["msg"] + k["open"] + k["close"] + r["dropped"] == offered
    assert r["marked"] == r["dropped"] == r["gauge"] > 0.7 * N
    assert r["gauge_max"] == r["max_seen"] and r["errors"] == 0
    assert r["late"] - r["early"] < 512 * 1024, f"la memoria creció {r['late'] - r['early']} B"


def test_same_flood_on_an_unbounded_queue_grows(monkeypatch):
    """Contraste: la medición sí detecta crecer (sin tope se acumula casi todo)."""
    monkeypatch.setattr(hft_ws, "RECONNECT_S", 0.01)
    r = asyncio.run(_flood(0))                      # asyncio.Queue(0) = sin tope
    assert r["dropped"] == 0 and r["max_seen"] > 0.7 * N
    assert r["late"] - r["early"] > 4 * 1024 * 1024


def test_slow_disk_holds_the_consumer_and_the_backlog_stays_bounded(monkeypatch, tmp_path):
    from eim.data.collectors import hft_writer
    gate, written = threading.Event(), Counter()

    def slow_write(root, kind, symbol, hour, rows):
        gate.wait(10)                               # disco «colgado» hasta abrir la compuerta
        written[kind] += len(rows)

    monkeypatch.setattr(hft_writer, "write_rows", slow_write)
    monkeypatch.setattr(hft_ws, "WRITE_BACKLOG_MAX", 40)        # filas sin escribir
    held0 = queues.gauge("hft.escritor").held

    async def go() -> dict:
        stop = asyncio.Event()
        store = HftStore(tmp_path, "BTCUSDT", flush_rows=10)
        inbox = hft_ws.Inbox(300, gauge=queues.Gauge(queues.BY_ID["hft.recepcion"]))
        cap = Cap(store)
        task = asyncio.create_task(hft_ws.consumer(inbox, cap, store, stop))
        peak, offered = 0, 0
        for i in range(3_000):                      # 10 por vuelta frente a un consumidor parado
            offered += inbox.offer("market", ("msg", "market", "{}", 0, 0), 0, 0)
            if i % 10 == 0:
                await asyncio.sleep(0)
                peak = max(peak, store.pending_rows)
        stalled = cap.kinds["msg"]
        gate.set()
        for _ in range(500):
            if inbox.q.empty() and store.pending_rows == 0:
                break
            await asyncio.sleep(0.01)
        alive = not task.done()
        stop.set()
        await asyncio.wait_for(task, 10)
        store.close()
        return {"peak": peak, "stalled": stalled, "inbox": inbox, "cap": cap, "alive": alive,
                "offered": offered, "rows": store.rows_written["bbo"]}

    r = asyncio.run(go())
    assert r["alive"]
    assert r["peak"] <= 40 + 10, f"filas sin escribir {r['peak']} con tope 40 (+1 volcado)"
    assert r["stalled"] <= 60, "el consumidor siguió consumiendo con el disco parado"
    assert r["inbox"].dropped == 3_000 - r["offered"] > 0      # lo pierde la recepción, contado
    assert r["rows"] == written["bbo"] == r["cap"].kinds["msg"]   # lo aceptado se escribe entero
    assert queues.gauge("hft.escritor").held > held0
