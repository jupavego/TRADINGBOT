"""Recolector Binance Futures (aggTrade + depth diffs). Proceso separado:

    python -m eim.data.collectors.binance_ws ETHUSDT --root data

Guarda trades, diffs de profundidad, top-10 del libro (≈1/s) y huecos de secuencia en
Parquet por hora. Si se rompe la secuencia o se corta la red, descarta el libro, registra el
hueco y resincroniza con un snapshot REST (reconexión con espera exponencial).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import httpx

from eim.data.collectors.book import LocalBook
from eim.data.collectors.writer import HourlyWriter

WS = "wss://fstream.binance.com/stream?streams={s}@aggTrade/{s}@depth@100ms"
REST = "https://fapi.binance.com/fapi/v1/depth"


class Collector:
    """Procesa mensajes ya decodificados (testeable sin red)."""

    def __init__(self, root, symbol: str, top_every_ms: int = 1000, flush_secs: float = 30.0):
        self.symbol, self.top_every_ms = symbol.upper(), top_every_ms
        self.w = {k: HourlyWriter(root, k, self.symbol, flush_secs=flush_secs)
                  for k in ("trades", "top", "depth", "gaps")}
        self.book = LocalBook()
        self.last_trade_id: int | None = None
        self._last_top = 0
        self.need_snapshot = True
        self.gaps = 0

    def gap(self, t: int, stream: str, detail: str) -> None:
        self.gaps += 1
        self.w["gaps"].add((t, stream, detail))

    def on_trade(self, d: dict) -> None:
        tid, t = int(d["a"]), int(d["T"])
        if self.last_trade_id is not None and tid != self.last_trade_id + 1:
            self.gap(t, "trades", f"esperado {self.last_trade_id + 1}, recibido {tid}")
        self.last_trade_id = tid
        self.w["trades"].add((t, tid, float(d["p"]), float(d["q"]), bool(d["m"])))

    def on_depth(self, d: dict) -> None:
        t = int(d.get("T") or d["E"])
        res = self.book.apply(int(d["U"]), int(d["u"]), int(d["pu"]), d["b"], d["a"])
        if res == "gap":
            self.gap(t, "depth", f"pu {d['pu']} != u previo; libro descartado")
            self.need_snapshot = True
            return
        if res != "ok":
            return
        for side, levels in (("b", d["b"]), ("a", d["a"])):
            for p, q in levels:
                self.w["depth"].add((t, int(d["U"]), int(d["u"]), int(d["pu"]), side,
                                     float(p), float(q)))
        if t - self._last_top >= self.top_every_ms and self.book.bids and self.book.asks:
            self._last_top = t
            bids, asks = self.book.top(10)
            self.w["top"].add((t, bids[0][0], bids[0][1], asks[0][0], asks[0][1],
                               json.dumps(bids), json.dumps(asks)))

    def on_message(self, msg: dict) -> None:
        d = msg.get("data", msg)
        if d.get("e") == "aggTrade":
            self.on_trade(d)
        elif d.get("e") == "depthUpdate":
            self.on_depth(d)

    def load_snapshot(self, snap: dict) -> None:
        self.book.load_snapshot(int(snap["lastUpdateId"]), snap["bids"], snap["asks"])
        self.need_snapshot = False

    def flush(self) -> None:
        for w in self.w.values():
            w.flush()


async def run(root, symbol: str, stop: asyncio.Event | None = None) -> None:
    import websockets

    col = Collector(root, symbol)
    backoff = 1.0
    stop = stop or asyncio.Event()
    async with httpx.AsyncClient(timeout=10) as http:
        while not stop.is_set():
            try:
                async with websockets.connect(WS.format(s=col.symbol.lower()),
                                              ping_interval=20, open_timeout=15) as ws:
                    backoff = 1.0
                    col.last_trade_id, col.need_snapshot = None, True
                    col.book.desync()
                    async for raw in ws:
                        col.on_message(json.loads(raw))
                        if col.need_snapshot:
                            r = await http.get(REST, params={"symbol": col.symbol, "limit": 1000})
                            r.raise_for_status()
                            col.load_snapshot(r.json())
                        if stop.is_set():
                            break
            except Exception as exc:  # corte de red, 429, etc. → registrar hueco y reintentar
                col.gap(int(time.time() * 1000), "ws", f"{type(exc).__name__}: {exc}"[:200])
                col.flush()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
    col.flush()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("symbol")
    ap.add_argument("--root", default="data")
    a = ap.parse_args()
    try:
        asyncio.run(run(a.root, a.symbol))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
