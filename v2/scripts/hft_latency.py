"""Banco de latencia HFT (T77): mide la ruta Binance → este equipo; nunca envía órdenes.

Uso (desde `v2/`):
  python scripts/hft_latency.py run --minutes 60 [--symbol BTCUSDT] [--label equipo-local]
  python scripts/hft_latency.py report      # fusiona reports/hft_latency/*.json → .md

Durante `--minutes` mide: RTT REST (`GET /fapi/v1/time`), desfase y deriva del reloj local
frente a `serverTime`; antigüedad (`E`/`T`) de cada evento de `depth@100ms` y `bookTicker`
(endpoint `/public`) y de `aggTrade` y `markPrice@1s` (`/market`); mensajes por segundo;
reconexiones; tiempo de proceso en Python (json + libro local en `depth`); retraso del bucle
asyncio; y RTT del WS API de órdenes solo con `ping`/`time`. Sin claves ni firmas: sirve igual
en otro equipo o VPS (solo medir). Estadística en `eim/hft/latency.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
import time
from array import array
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from eim.data.collectors.book import LocalBook  # noqa: E402
from eim.hft.latency import (  # noqa: E402
    ClockSample,
    Hist,
    clock_anchors,
    clock_summary,
    event_times,
    stream_kind,
    stream_stats,
)
from eim.hft.latency_report import render  # noqa: E402

FAPI = "https://fapi.binance.com"
WS = {"public": "wss://fstream.binance.com/public/stream?streams={s}@depth@100ms/{s}@bookTicker",
      "market": "wss://fstream.binance.com/market/stream?streams={s}@aggTrade/{s}@markPrice@1s"}
WS_API = "wss://ws-fapi.binance.com/ws-fapi/v1"
KINDS = ("depth", "bookTicker", "aggTrade", "markPrice")
OUT = ROOT / "reports" / "hft_latency"
SNAPSHOT_MIN_S = 5.0               # snapshot REST de profundidad: peso 20, como mucho cada 5 s


def now_us() -> int:
    return time.time_ns() // 1000


class Capture:
    """Acumula lo crudo; el resumen se calcula al final (reloj corregido a posteriori)."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol.upper()
        self.ev = {k: (array("q"), array("q"), array("q")) for k in KINDS}
        self.proc = {k: Hist(1.0) for k in KINDS}                 # µs
        self.clock: list[ClockSample] = []
        self.wsapi = {"ping": Hist(1.0), "time": Hist(1.0)}       # ms
        self.loop_lag = Hist(0.1)                                 # ms
        self.conns = {n: {"opens": 0, "down_s": 0.0, "errors": []} for n in (*WS, "ws_api", "rest")}
        self.book, self.need_snapshot = LocalBook(), True
        self.book_gaps = self.snapshots = 0

    def reset_book(self) -> None:
        self.book.desync()
        self.need_snapshot = True

    def on_raw(self, raw: str | bytes, recv_us: int) -> None:
        t0 = time.perf_counter_ns()
        msg = json.loads(raw)
        d = msg.get("data", msg)
        kind = stream_kind(msg.get("stream", ""))
        if kind not in self.ev:
            return
        ok = True
        if kind == "depth":
            res = self.book.apply(int(d["U"]), int(d["u"]), int(d["pu"]), d["b"], d["a"])
            ok = res == "ok"                    # el proceso de `depth` se mide con libro vivo
            if res == "gap":
                self.book_gaps += 1
                self.need_snapshot = True
        elif kind == "bookTicker":
            float(d["b"]), float(d["a"])
        elif kind == "aggTrade":
            float(d["p"]), float(d["q"])
        e, t = event_times(kind, d)
        loc, es, ts = self.ev[kind]
        loc.append(recv_us)
        es.append(e)
        ts.append(t)
        if ok:
            self.proc[kind].add((time.perf_counter_ns() - t0) / 1000)

    def error(self, conn: str, exc: BaseException) -> None:
        errs = self.conns[conn]["errors"]
        if len(errs) < 50:
            errs.append([datetime.now(UTC).isoformat(timespec="seconds"),
                         f"{type(exc).__name__}: {exc}"[:160]])


async def stream_task(cap: Capture, name: str, url: str, on_open=None) -> None:
    import websockets

    backoff, down_since = 1.0, None
    while True:
        try:
            async with websockets.connect(url, open_timeout=15, ping_interval=20) as ws:
                c = cap.conns[name]
                c["opens"] += 1
                if down_since is not None:
                    c["down_s"] += time.monotonic() - down_since
                    down_since = None
                if on_open:
                    on_open()
                backoff = 1.0
                async for raw in ws:
                    cap.on_raw(raw, now_us())
            cap.error(name, ConnectionError("cierre limpio del servidor"))   # p. ej. a las 24 h
            down_since = time.monotonic()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # corte, 1008, timeout… → se registra y se reconecta
            cap.error(name, exc)
            down_since = down_since if down_since is not None else time.monotonic()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)


async def snapshot_task(cap: Capture, http: httpx.AsyncClient) -> None:
    last = 0.0
    while True:
        if cap.need_snapshot and time.monotonic() - last >= SNAPSHOT_MIN_S:
            last = time.monotonic()
            try:
                r = await http.get("/fapi/v1/depth", params={"symbol": cap.symbol, "limit": 1000})
                r.raise_for_status()
                s = r.json()
                cap.book.load_snapshot(int(s["lastUpdateId"]), s["bids"], s["asks"])
                cap.need_snapshot = False
                cap.snapshots += 1
            except Exception as exc:
                cap.error("rest", exc)
        await asyncio.sleep(0.2)


async def clock_task(cap: Capture, http: httpx.AsyncClient, every_s: float) -> None:
    while True:
        try:
            s = now_us()
            r = await http.get("/fapi/v1/time")
            e = now_us()
            r.raise_for_status()
            cap.clock.append(ClockSample(s, e, int(r.json()["serverTime"])))
        except Exception as exc:
            cap.error("rest", exc)
        await asyncio.sleep(every_s)


async def wsapi_task(cap: Capture, every_s: float) -> None:
    import websockets

    i, backoff = 0, 1.0
    while True:
        try:
            async with websockets.connect(WS_API, open_timeout=15, ping_interval=20) as ws:
                cap.conns["ws_api"]["opens"] += 1
                backoff = 1.0
                while True:
                    for meth in ("ping", "time"):
                        i += 1
                        t = time.perf_counter_ns()
                        await ws.send(json.dumps({"id": str(i), "method": meth}))
                        r = json.loads(await asyncio.wait_for(ws.recv(), 10))
                        if r.get("status") == 200:
                            cap.wsapi[meth].add((time.perf_counter_ns() - t) / 1e6)
                    await asyncio.sleep(every_s)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            cap.error("ws_api", exc)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)


async def loop_lag_task(cap: Capture, every_s: float = 0.1) -> None:
    while True:
        t = time.perf_counter()
        await asyncio.sleep(every_s)
        cap.loop_lag.add((time.perf_counter() - t - every_s) * 1000)


async def progress_task(cap: Capture, minutes: float) -> None:
    t0 = time.monotonic()
    while True:
        await asyncio.sleep(600)
        n = {k: len(v[0]) for k, v in cap.ev.items()}
        print(f"[{(time.monotonic() - t0) / 60:.0f}/{minutes:.0f} min] {n} "
              f"reloj={len(cap.clock)} huecos_libro={cap.book_gaps}", flush=True)


async def capture(symbol: str, minutes: float, sync_s: float, api_s: float) -> Capture:
    cap = Capture(symbol)
    s = cap.symbol.lower()
    async with httpx.AsyncClient(base_url=FAPI, timeout=10) as http:
        tasks = [asyncio.create_task(c) for c in (
            clock_task(cap, http, sync_s), snapshot_task(cap, http),
            stream_task(cap, "public", WS["public"].format(s=s), cap.reset_book),
            stream_task(cap, "market", WS["market"].format(s=s)),
            wsapi_task(cap, api_s), loop_lag_task(cap), progress_task(cap, minutes))]
        await asyncio.sleep(minutes * 60)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return cap


def summarize(cap: Capture, meta: dict, duration_s: float) -> dict:
    anchors = clock_anchors(cap.clock)
    streams, hists = {}, {}
    for k in KINDS:
        loc, e, t = cap.ev[k]
        out, h = stream_stats(loc, e, t, anchors, duration_s, cap.proc[k])
        streams[k] = out
        hists[k] = {n: x.to_json() for n, x in h.items()}
    rest = Hist.of(s.rtt_ms for s in cap.clock[1:])          # la 1.ª incluye el TLS
    hists.update(rest_rtt=rest.to_json(), ws_api_ping=cap.wsapi["ping"].to_json(),
                 ws_api_time=cap.wsapi["time"].to_json(), loop_lag=cap.loop_lag.to_json())
    conns = {n: {"reconnects": max(c["opens"] - 1, 0), "down_s": round(c["down_s"], 1),
                 "errors": c["errors"]} for n, c in cap.conns.items()}
    return {"version": 1, **meta, "duration_s": round(duration_s, 1),
            "clock": clock_summary(cap.clock, anchors), "rest_rtt_ms": rest.summary(),
            "rest_rtt_cold_ms": round(cap.clock[0].rtt_ms, 1) if cap.clock else None,
            "ws_api_rtt_ms": {m: h.summary() for m, h in cap.wsapi.items()},
            "loop_lag_ms": cap.loop_lag.summary(2), "connections": conns,
            "book": {"gaps": cap.book_gaps, "snapshots": cap.snapshots},
            "streams": streams, "hists": hists}


def write_report(out_dir: Path) -> Path:
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out_dir.glob("*.json"))]
    md = out_dir.parent / f"{out_dir.name}.md"
    md.write_text(render(runs), encoding="utf-8")
    return md


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="medir y guardar una corrida")
    r.add_argument("--minutes", type=float, default=60.0)
    r.add_argument("--symbol", default="BTCUSDT")
    r.add_argument("--label", default="equipo-local", help="nombre del equipo o VPS")
    r.add_argument("--note", default="", help="contexto (p. ej. «con el servicio continuo»)")
    r.add_argument("--sync-s", type=float, default=5.0, help="cada cuántos s GET /fapi/v1/time")
    r.add_argument("--api-s", type=float, default=5.0, help="cada cuántos s ping/time al WS API")
    r.add_argument("--out", type=Path, default=OUT)
    rep = sub.add_parser("report", help="fusionar las corridas en el Markdown")
    rep.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    if a.cmd == "report":
        print(write_report(a.out))
        return
    start = datetime.now(UTC)
    t0 = time.monotonic()
    try:
        cap = asyncio.run(capture(a.symbol, a.minutes, a.sync_s, a.api_s))
    except KeyboardInterrupt:
        sys.exit("interrumpido: sin informe")
    meta = {"run_id": f"{start:%Y%m%dT%H%MZ}_{a.label}", "label": a.label, "note": a.note,
            "symbol": cap.symbol, "started_utc": start.isoformat(timespec="seconds"),
            "ended_utc": datetime.now(UTC).isoformat(timespec="seconds"), "minutes": a.minutes,
            "host": {"platform": platform.platform(), "python": platform.python_version(),
                     "cpus": os.cpu_count()}}
    res = summarize(cap, meta, time.monotonic() - t0)
    a.out.mkdir(parents=True, exist_ok=True)
    path = a.out / f"{meta['run_id']}.json"
    path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"corrida: {path}\ninforme: {write_report(a.out)}")


if __name__ == "__main__":
    main()
