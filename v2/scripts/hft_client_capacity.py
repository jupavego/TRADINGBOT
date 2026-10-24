"""Capacidad del cliente del banco de latencia (T77): ¿cuántos mensajes/s consume Python?

Uso (desde `v2/`): python scripts/hft_client_capacity.py [--n 200000] [--reps 2]
Lanza un servidor WebSocket local en otro proceso que envía `n` mensajes `bookTicker` reales
(mismo formato que Binance) lo más rápido posible, y los consume con el MISMO manejador del banco
(`Capture.on_raw` de `scripts/hft_latency.py`). Si la capacidad supera con holgura la tasa de
las ráfagas medidas, la cola de antigüedad en ráfagas no es del proceso en Python. Sin red
externa; sin TLS (cota optimista del cliente). Escribe `reports/hft_client_capacity.json`.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MSG = ('{{"stream":"btcusdt@bookTicker","data":{{"e":"bookTicker","u":11905344823631,'
       '"s":"BTCUSDT","ps":"BTCUSDT","b":"81385.00","B":"2.502","a":"81385.10","A":"2.478",'
       '"T":{t},"E":{t},"st":1}}}}')


async def serve(port: int, n: int) -> None:
    import websockets

    done = asyncio.Event()

    async def handler(ws) -> None:
        for _ in range(n):
            await ws.send(MSG.format(t=time.time_ns() // 1_000_000))
        await ws.close()
        done.set()

    async with websockets.serve(handler, "127.0.0.1", port):
        await done.wait()


async def consume(port: int) -> dict:
    import websockets

    spec = importlib.util.spec_from_file_location("hft_latency",
                                                  ROOT / "scripts" / "hft_latency.py")
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    cap, t0 = bench.Capture("BTCUSDT"), None
    for _ in range(50):                                   # el servidor tarda en arrancar
        try:
            ws = await websockets.connect(f"ws://127.0.0.1:{port}")
            break
        except OSError:
            await asyncio.sleep(0.2)
    async with ws:
        async for raw in ws:
            t0 = t0 or time.perf_counter()
            cap.on_raw(raw, bench.now_us())
    secs = time.perf_counter() - t0
    n = len(cap.ev["bookTicker"][0])
    return {"msgs": n, "secs": round(secs, 2), "msg_per_s": round(n / secs),
            "proc_p99_us": cap.proc["bookTicker"].quantile(0.99)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=200_000)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.serve:
        asyncio.run(serve(a.port, a.n))
        return
    runs = []
    for _ in range(a.reps):
        srv = subprocess.Popen([sys.executable, __file__, "--serve", "--port", str(a.port),
                                "--n", str(a.n)])
        try:
            runs.append(asyncio.run(consume(a.port)))
        finally:
            srv.wait(timeout=60)
    out = {"measured_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "host": {"platform": platform.platform(), "python": platform.python_version()},
           "runs": runs, "min_msg_per_s": min(r["msg_per_s"] for r in runs)}
    path = ROOT / "reports" / "hft_client_capacity.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
