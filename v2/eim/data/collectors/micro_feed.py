"""Microestructura derivada de la captura HFT (T128, entregable 1).

El recolector viejo (`binance_ws`, T23) abría otras dos conexiones a Binance para el mismo
símbolo y llevaba su propio libro para lo mismo que ya hace la captura HFT. Además guardaba
cada nivel de cada diff como una fila, y gastaba ~11 % de la CPU del equipo frente al ~1 % de
la captura. Ahora `hft_ws` alimenta este feed con su libro verificado: una foto top-10 cada
segundo en `data/micro/top` (el mismo formato que antes) y el latido `data/micro/heartbeat.json`
para el panel. Los trades y los huecos los lee `eim.data.micro` directamente de `micro_hft`.

La captura no espera nunca al feed: `on_book` solo acumula y `flush` se llama desde un hilo.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from eim.data.collectors.book import LocalBook
from eim.data.collectors.health import write_heartbeat
from eim.data.collectors.writer import HourlyWriter

TOP_EVERY_MS = 1000


class MicroFeed:
    def __init__(self, root: str | Path, symbol: str, top_every_ms: int = TOP_EVERY_MS) -> None:
        self.root, self.symbol, self.every = Path(root), symbol.upper(), top_every_ms
        self._w = HourlyWriter(self.root, "top", self.symbol, flush_rows=10**9,
                               flush_secs=float("inf"))  # vuelca solo `flush`
        self._buf: list[tuple] = []
        self._last = 0
        self.tops = 0
        self.started_at = int(time.time() * 1000)

    def on_book(self, t_ms: int, book: LocalBook) -> None:
        """Tras cada diff aplicado al libro sincronizado (hora del evento de Binance)."""
        if t_ms - self._last < self.every or not book.bids or not book.asks:
            return
        self._last = t_ms
        bids, asks = book.top(10)
        self._buf.append((t_ms, bids[0][0], bids[0][1], asks[0][0], asks[0][1],
                          json.dumps(bids), json.dumps(asks)))
        self.tops += 1

    def flush(self) -> None:
        """Escribe lo acumulado (Parquet por hora). Seguro desde otro hilo: el cambio de lista
        es atómico y lo que `on_book` añada después va a la lista nueva."""
        rows, self._buf = self._buf, []
        if rows:
            self._w.buf = rows
            self._w.flush()

    def heartbeat(self, status: dict) -> None:
        """El latido de siempre del recolector de microestructura, con las cifras de la captura."""
        counts = status.get("counts") or {}
        write_heartbeat(self.root, {
            "last_heartbeat": int(time.time() * 1000), "pid": os.getpid(), "symbol": self.symbol,
            "started_at": self.started_at, "last_msg_ms": status.get("last_msg_ms"),
            "trades": counts.get("trades", 0), "depth_msgs": counts.get("depth", 0),
            "gaps": sum((status.get("gaps") or {}).values()), "tops": self.tops,
            "source": "hft_ws"}, self.symbol)
