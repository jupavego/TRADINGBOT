"""La cantera como variante del bróker simulado (T168). Apagada por defecto (`EIM_NURSERY=0`).

Patrón de `paper/variant.py`: no genera contextos ni sincroniza velas (lo hace la mesa principal,
que con `EIM_NURSERY=1` guarda además las variables nativas), lee los contextos de `paper.duckdb`
y escribe solo en su base propia. Opera sobre el **precio real en vivo**: el camino de 15 m y el
funding del mismo almacén que usa el bróker. No registra intentos en la puerta de T49, no emite
al Observatorio ni a `op_alerts` y no pesa en la síntesis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path as FsPath

import numpy as np

from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import FOCUS, tf_ms
from eim.nursery.book import Book, run_book
from eim.nursery.params import LABEL, NAME, NurseryParams
from eim.nursery.prospect import Prospect, load_prospects
from eim.nursery.signals import accounts_for
from eim.nursery.store import NurseryStore, light_contexts
from eim.nursery.summary import summarize
from eim.paper.engine import Path
from eim.paper.generate import now_ms

_log = logging.getLogger("eim.nursery")
WARM_BARS = 8                 # contextos previos al inicio para que las reglas vean su historia


def load_path(store: Store, symbol: str, path_tf: str, start: int) -> Path:
    """Camino real (15 m) desde `start` con el funding real del almacén."""
    p = Path.from_arrays(store.read_arrays(symbol, path_tf, start=start), tf_ms(path_tf))
    fund = store.read_series("funding", symbol, start=start - 8 * 3_600_000)
    p.ft = np.array([t for t, _ in fund], dtype=np.int64)
    p.fr = np.array([x for _, x in fund], dtype=float)
    return p


class NurseryDesk:
    def __init__(self, store: Store, ctx_store: PaperStore, own_store: PaperStore, *,
                 params: NurseryParams | None = None,
                 prospects: tuple[Prospect, ...] | None = None,
                 symbol: str = FOCUS[0], poll_s: float = 300.0) -> None:
        self.store, self.ctx_store, self.pstore = store, ctx_store, own_store
        self.params = params or NurseryParams()
        self.prospects = prospects if prospects is not None else load_prospects()
        self.symbol, self.poll_s = symbol, poll_s
        self.name, self.label = NAME, LABEL
        self.tfs = tuple(sorted({p.timeframe for p in self.prospects}))
        self.book_store = NurseryStore(own_store)
        self.last_tick: int | None = None
        self.live_error = ""
        self._stamp: tuple | None = None
        self._summary: dict | None = None
        self._lock = threading.Lock()

    def live_status(self) -> dict:
        return {"last_tick": self.last_tick, "error": self.live_error, "poll_s": self.poll_s}

    def compute(self, now: int | None = None) -> Book:
        """Recalcula el libro con lo que haya y lo guarda en la base propia."""
        p = self.params
        at = now_ms() if now is None else now
        registered = self.book_store.register(accounts_for(self.prospects), at)
        warm = max(tf_ms(tf) for tf in self.tfs) * WARM_BARS
        start = max(p.start_ms, min(registered.values(), default=p.start_ms))
        ctxs = {tf: light_contexts(self.ctx_store, self.symbol, tf, start - warm)
                for tf in self.tfs}
        path = load_path(self.store, self.symbol, p.exec.path_tf, start - warm)
        book = run_book(ctxs, path, self.prospects, p.model_copy(update={"start_ms": start}),
                        registered)
        self.book_store.save(book)
        first = next((c for c in ctxs.get(self.tfs[0], []) if c["t"] >= start), None)
        with self._lock:
            self._summary = summarize(book, path, first)
        return book

    def summary(self) -> dict | None:
        with self._lock:
            return self._summary

    def tick(self) -> None:
        stamp = tuple(self.ctx_store.stamp(self.symbol, tf) for tf in self.tfs)
        if stamp != self._stamp:
            self.compute()
            self._stamp = stamp
        self.last_tick, self.live_error = now_ms(), ""
        self._beat()

    def heartbeat_path(self) -> FsPath:
        return FsPath(self.store.root) / "paper" / f"heartbeat_{self.name}.json"

    def _beat(self) -> None:
        try:
            hp = self.heartbeat_path()
            hp.parent.mkdir(parents=True, exist_ok=True)
            hp.write_text(json.dumps({"last_tick": self.last_tick, "name": self.name,
                                      "error": self.live_error}), encoding="utf-8")
        except OSError:
            pass      # el latido nunca tumba el ciclo

    async def loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.tick)
            except Exception as exc:  # noqa: BLE001 — la cantera nunca tumba la API
                self.live_error = f"{type(exc).__name__}: {exc}"
                _log.warning("cantera: %s", self.live_error)
                self._beat()
            await asyncio.sleep(self.poll_s)
