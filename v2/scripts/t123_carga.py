"""T123: memoria del proceso con un productor 10× más rápido, antes y después de acotar.

    python -I scripts/t123_carga.py --secs 20 [--json salida.json]

Cada escenario corre en un proceso aparte (memoria limpia) y se mide la memoria privada del
propio proceso cada segundo (`eim.operation.usage_win`, sin estimar):

- `recepcion`: `reader` + `consumer` reales de la captura HFT; un WebSocket falso entrega 640
  mensajes de 300 B por vuelta y el consumidor (que decodifica JSON) procesa 64. Antes = cola sin
  tope (`maxsize=0`); después = la `Inbox` de 50 000 de T123.
- `escritor`: disco parado (la escritura no vuelve) y el consumidor añadiendo filas. Antes = sin
  frenar (lo que hacía el código hasta T123); después = frena a 200 000 filas sin escribir.

Un escenario «antes» se corta si pasa de `--tope-mb` para no ahogar el equipo (T141).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eim.data.collectors import hft_writer, hft_ws  # noqa: E402
from eim.data.collectors.hft_writer import HftStore  # noqa: E402
from eim.operation import usage_win  # noqa: E402

RAW = json.dumps({"e": "depthUpdate", "b": [["1", "2"]] * 18})[:300]


def mem_mb() -> float:
    return usage_win.snapshot()[os.getpid()].commit / 1e6


class Clock:
    def now(self) -> tuple[int, int]:
        return time.time_ns(), time.monotonic_ns()


class Flood:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        i = 0
        while True:
            if i % 640 == 0:
                await asyncio.sleep(0)
            i += 1
            yield RAW


class Cap:
    def __init__(self, store=None) -> None:
        self.counts: dict[str, int] = {"errores_proceso": 0}
        self.n, self.store = 0, store

    def handle(self, item: tuple) -> None:
        if item[0] == "msg":
            json.loads(item[2])
            self.n += 1
            if self.store is not None:
                self.store.add("bbo", 0, (time.time_ns(), 1, 2, 3, 4.0, 5.0, 6.0, 7.0))


class NoStore:
    backlog = pending_rows = 0

    def maybe_flush(self) -> None:
        pass


async def scenario(name: str, bounded: bool, secs: float, cap_mb: float) -> dict:
    stop = asyncio.Event()
    inbox = hft_ws.Inbox(hft_ws.QUEUE_MAX if (bounded or name == "escritor") else 0)
    store = None
    if name == "escritor":
        hft_writer.write_rows = lambda *a, **k: threading.Event().wait(3600)   # disco parado
        hft_ws.WRITE_BACKLOG_MAX = hft_ws.WRITE_BACKLOG_MAX if bounded else 10**12
        store = HftStore(Path(tempfile.gettempdir()) / "t123_nada", "BTCUSDT", flush_rows=5_000)
    cap = Cap(store)
    tasks = [asyncio.create_task(hft_ws.reader("market", "ws://x", inbox, Clock(), stop,
                                               connect=lambda url, **kw: Flood())),
             asyncio.create_task(hft_ws.consumer(inbox, cap, store or NoStore(), stop))]
    samples, t0, cut = [], time.monotonic(), False
    while time.monotonic() - t0 < secs:
        await asyncio.sleep(1.0)
        samples.append(round(mem_mb(), 1))
        if samples[-1] > cap_mb:
            cut = True
            break
    alive = all(not t.done() for t in tasks)
    stop.set()
    for t in tasks:
        t.cancel()
    return {"escenario": name, "acotado": bounded, "segundos": len(samples), "cortado": cut,
            "mb_inicio": samples[0], "mb_max": max(samples), "mb_final": samples[-1],
            "mb_ultimos_5s": samples[-5:], "procesados": cap.n, "descartados": inbox.dropped,
            "cola_max": inbox.max_seen, "filas_sin_escribir": store.pending_rows if store else 0,
            "etapas_vivas": alive}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--secs", type=float, default=20.0)
    ap.add_argument("--tope-mb", type=float, default=900.0)
    ap.add_argument("--json")
    ap.add_argument("--uno", nargs=2, metavar=("ESCENARIO", "ACOTADO"), help=argparse.SUPPRESS)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")   # consola de Windows en cp1252
    if a.uno:
        r = asyncio.run(scenario(a.uno[0], a.uno[1] == "1", a.secs, a.tope_mb))
        print(json.dumps(r, ensure_ascii=False), flush=True)
        os._exit(0)                     # el hilo del disco parado no debe retener el proceso
    out = []
    for name in ("recepcion", "escritor"):
        for bounded in (False, True):
            p = subprocess.run([sys.executable, "-I", __file__, "--secs", str(a.secs),
                                "--tope-mb", str(a.tope_mb), "--uno", name, str(int(bounded))],
                               capture_output=True, text=True, encoding="utf-8")
            r = json.loads(p.stdout.strip().splitlines()[-1])
            out.append(r)
            cut = " (cortado)" if r["cortado"] else ""
            print(f"{name:9} {'después' if bounded else 'antes  '}: {r['mb_inicio']:7.1f} → "
                  f"máx {r['mb_max']:7.1f} MB en {r['segundos']} s{cut} · procesados "
                  f"{r['procesados']} · descartados {r['descartados']} · cola máx "
                  f"{r['cola_max']} · filas sin escribir {r['filas_sin_escribir']}", flush=True)
    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
