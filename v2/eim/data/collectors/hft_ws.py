"""Captura HFT de Binance USDⓈ-M (T78). Proceso separado, amplía el recolector T23 sin tocarlo:

    python -m eim.data.collectors.hft_ws BTCUSDT --root data [--check-s 300]

Escribe en `data/micro_hft/` (la partición `micro/` de T23 queda igual): todos los diffs de
`depth@100ms`, `bookTicker`, `aggTrade`, `markPrice@1s` y `forceOrder`, cada uno con el reloj del
exchange y el local de recepción; snapshots REST para sincronizar y, cada `--check-s`, para
verificar el libro reconstruido. Tres conexiones (`/public` depth, `/public` bookTicker,
`/market` el resto) sellan cada mensaje al llegar y lo dejan en una cola acotada: si se llena se
descarta y el tramo queda marcado (`cola_llena`), nunca se bloquea la recepción. Latido en
`data/micro_hft/heartbeat.json`; lo vigila `eim.data.collectors.hft_supervise`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path

import httpx

from eim.data.collectors import health
from eim.data.collectors.hft_capture import HftCapture
from eim.data.collectors.hft_clock import CHECK_S as CLOCK_EVERY_S
from eim.data.collectors.hft_clock import RecvClock
from eim.data.collectors.hft_schema import AREA
from eim.data.collectors.hft_writer import COMPONENT, HftStore
from eim.observability import hooks_service
from eim.observability.emit import configure
from eim.operation.watchdog import instance_lock

WS = {"depth": "wss://fstream.binance.com/public/stream?streams={s}@depth@100ms",
      "bbo": "wss://fstream.binance.com/public/stream?streams={s}@bookTicker",
      "market": "wss://fstream.binance.com/market/stream?streams={s}@aggTrade/{s}@markPrice@1s/"
                "{s}@forceOrder"}
REST = "https://fapi.binance.com/fapi/v1/depth"
QUEUE_MAX = 50_000            # ~40 s de ráfaga de bookTicker; más sería memoria sin límite
CHECK_EVERY_S = 300.0         # snapshot de verificación (peso 20 de 2 400/min)
SYNC_MIN_GAP_S = 1.0          # espera mínima entre snapshots de sincronía (crece si fallan)
RECONNECT_S = 1.0             # primera espera tras un corte (se duplica hasta 60 s)


async def _nap(stop: asyncio.Event, seconds: float) -> None:
    """Duerme `seconds` o hasta que se pida parar."""
    try:
        await asyncio.wait_for(stop.wait(), seconds)
    except TimeoutError:
        pass


class Inbox:
    """Cola acotada entre recepción y proceso. Lleno ⇒ el mensaje se descarta y, en cuanto hay
    sitio, entra una marca `overflow` con cuántos y entre qué instantes."""

    def __init__(self, maxsize: int = QUEUE_MAX) -> None:
        self.q: asyncio.Queue = asyncio.Queue(maxsize)
        self.drops: dict[str, list[int]] = {}
        self.dropped = 0
        self.max_seen = 0

    def offer(self, conn: str, item: tuple, recv: int, mono: int) -> bool:
        if conn in self.drops and self.q.maxsize - self.q.qsize() >= 2:
            n, start, end = self.drops.pop(conn)
            self.q.put_nowait(("overflow", conn, n, start, end, recv, mono))
        try:
            self.q.put_nowait(item)
        except asyncio.QueueFull:
            d = self.drops.setdefault(conn, [0, recv, recv])
            d[0] += 1
            d[2] = recv
            self.dropped += 1
            return False
        self.max_seen = max(self.max_seen, self.q.qsize())
        return True


async def reader(name: str, url: str, inbox: Inbox, clock: RecvClock, stop: asyncio.Event,
                 connect=None) -> None:
    """Una conexión con reintentos (espera exponencial); cada corte queda en la cola."""
    if connect is None:
        import websockets
        connect = websockets.connect
    backoff = RECONNECT_S
    while not stop.is_set():
        err = "cerrada por el servidor"
        try:
            async with connect(url, ping_interval=20, open_timeout=15, max_size=2**23) as ws:
                backoff = RECONNECT_S
                inbox.offer(name, ("open", name), *clock.now())
                async for raw in ws:
                    recv, mono = clock.now()
                    inbox.offer(name, ("msg", name, raw, recv, mono), recv, mono)
                    if stop.is_set():
                        return
        except Exception as exc:  # corte de red, 429, etc. → marcar y reintentar
            err = f"{type(exc).__name__}: {exc}"[:200]
            hooks_service.service_error(COMPONENT, exc, detail={"conn": name})
        recv, mono = clock.now()
        inbox.offer(name, ("close", name, err, recv, mono), recv, mono)
        await _nap(stop, backoff)
        backoff = min(backoff * 2, 60.0)


async def consumer(inbox: Inbox, cap: HftCapture, store: HftStore, stop: asyncio.Event) -> None:
    """Procesa la cola en orden; cede el bucle cada 64 mensajes para que la recepción selle."""
    n = 0
    while not (stop.is_set() and inbox.q.empty()):
        try:
            item = await asyncio.wait_for(inbox.q.get(), timeout=1.0)
        except TimeoutError:
            store.maybe_flush()
            continue
        try:
            cap.handle(item)
        except Exception as exc:  # noqa: BLE001 - un mensaje raro no detiene la captura
            cap.counts["errores_proceso"] += 1
            hooks_service.service_error(COMPONENT, exc, detail={"item": str(item[0])})
        n += 1
        if n % 64 == 0:
            store.maybe_flush()
            await asyncio.sleep(0)


async def snapshots(cap: HftCapture, inbox: Inbox, http, clock: RecvClock, stop: asyncio.Event,
                    check_s: float = CHECK_EVERY_S, url: str = REST) -> None:
    """Snapshot de sincronía cuando el libro lo pide; de verificación cada `check_s`."""
    next_check = time.monotonic() + min(check_s, 60.0)
    last_req, gap_s = 0.0, SYNC_MIN_GAP_S
    while not stop.is_set():
        await asyncio.sleep(0.2)
        now = time.monotonic()
        sync = cap.wants_sync()
        if not sync and not (cap.vb.book.synced and now >= next_check):
            gap_s = SYNC_MIN_GAP_S
            continue
        if now - last_req < (gap_s if sync else SYNC_MIN_GAP_S):
            continue
        last_req = now
        if sync:
            gap_s = min(gap_s * 2, 60.0)
        req, _ = clock.now()
        try:
            r = await http.get(url, params={"symbol": cap.symbol, "limit": 1000})
            r.raise_for_status()
            snap = r.json()
        except Exception as exc:  # noqa: BLE001 - se reintenta con espera creciente
            cap.counts["snap_errores"] += 1
            hooks_service.service_error(COMPONENT, exc, detail={"rest": "depth"})
            continue
        recv, mono = clock.now()
        before = cap.snaps_handled
        if not inbox.offer("rest", ("snap", "sync" if sync else "check", snap, req, recv, mono),
                           recv, mono):
            continue
        if not sync:
            next_check = now + check_s
        for _ in range(100):                     # que el proceso lo cargue antes de decidir otro
            if cap.snaps_handled > before or stop.is_set():
                break
            await asyncio.sleep(0.05)


async def clock_task(clock: RecvClock, inbox: Inbox, stop: asyncio.Event) -> None:
    while not stop.is_set():
        await _nap(stop, CLOCK_EVERY_S)
        res = clock.check()
        if res:
            recv, mono = clock.now()
            inbox.offer("clock", ("clock", *res, recv, mono), recv, mono)


def heartbeat(root, cap: HftCapture, inbox: Inbox, store: HftStore, started_ms: int) -> None:
    health.write_heartbeat(root, {
        "last_heartbeat": int(time.time() * 1000), "pid": os.getpid(), "symbol": cap.symbol,
        "started_at": started_ms, "queue": inbox.q.qsize(), "queue_max": inbox.max_seen,
        "dropped": inbox.dropped, "write_backlog": store.backlog, "write_errors": store.errors,
        "write_last_error": store.last_error, **cap.status()}, cap.symbol, area=AREA)


async def run(root, symbol: str, stop: asyncio.Event | None = None,
              check_s: float = CHECK_EVERY_S, connect=None, http=None) -> None:
    stop = stop or asyncio.Event()
    clock = RecvClock()
    run_ns = clock.now()[0]
    store = HftStore(root, symbol)
    cap = HftCapture(symbol, store, run_ns)
    inbox = Inbox()
    s = cap.symbol.lower()

    async def beat() -> None:
        while not stop.is_set():
            heartbeat(root, cap, inbox, store, run_ns // 1_000_000)
            await _nap(stop, health.HEARTBEAT_EVERY_S)
        heartbeat(root, cap, inbox, store, run_ns // 1_000_000)

    async def all_tasks(client) -> None:
        await asyncio.gather(
            consumer(inbox, cap, store, stop), beat(), clock_task(clock, inbox, stop),
            snapshots(cap, inbox, client, clock, stop, check_s),
            *(reader(n, u.format(s=s), inbox, clock, stop, connect) for n, u in WS.items()))

    try:
        if http is not None:
            await all_tasks(http)
        else:
            async with httpx.AsyncClient(timeout=10) as client:
                await all_tasks(client)
    finally:
        store.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbol")
    ap.add_argument("--root", default="data")
    ap.add_argument("--check-s", type=float, default=CHECK_EVERY_S)
    a = ap.parse_args()
    configure(process="hft_collector", spool_dir=Path(a.root) / "obs" / "spool")
    lock = instance_lock(health.area_dir(a.root, AREA) / f"collector{health.sfx(a.symbol)}.lock")
    if lock is None:
        print("Ya hay una captura HFT de este símbolo en esta carpeta de datos.", flush=True)
        raise SystemExit(3)
    try:
        asyncio.run(run(a.root, a.symbol, check_s=a.check_s))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
