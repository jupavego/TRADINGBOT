"""Libro verificado de la captura HFT (T78). Puro: sin red ni disco.

Envuelve el `LocalBook` de T23 con el procedimiento oficial completo de Binance:
- mientras espera un snapshot REST **acumula** los diffs (cola acotada) y, al cargarlo, aplica los
  que siguen y descarta los `u < lastUpdateId`: el snapshot puede llegar tarde sin perder sincronía;
- **verifica** la reconstrucción con snapshots REST periódicos. El snapshot con `lastUpdateId = L`
  más el diff que contiene `L` (`U ≤ L ≤ u`) da el libro exacto en `u` (los diffs traen la
  cantidad final de cada nivel tocado), y se compara con el libro local en ese mismo `u`: top-N,
  precio y cantidad exactos. Si difieren hay un libro fantasma: la comparación queda registrada y
  el libro se rehace desde el snapshot más los diffs ya aplicados después (nunca se sigue
  operando sobre un libro dudoso).
"""

from __future__ import annotations

import hashlib
import heapq
import struct
from collections import deque
from dataclasses import dataclass
from itertools import zip_longest

from eim.data.collectors.book import LocalBook

TOP_N = 10
RING_MAX = 600       # diffs aplicados que se recuerdan (~60 s a 100 ms) para casar un snapshot
PENDING_MAX = 600    # diffs que se acumulan mientras llega un snapshot

Level = tuple[float, float]
Top = tuple[tuple[Level, ...], tuple[Level, ...]]


@dataclass(frozen=True)
class Diff:
    first: int
    last: int
    prev: int
    bids: list[Level]
    asks: list[Level]


@dataclass(frozen=True)
class Check:
    snap_id: int
    at_id: int          # `u` del diff con el que se comparó (−1 si no fue comparable)
    comparable: bool
    match: bool
    n_diff: int         # posiciones del top-N que difieren (precio o cantidad)
    detail: str


def top_of(bids: dict[float, float], asks: dict[float, float], n: int = TOP_N) -> Top:
    return tuple(heapq.nlargest(n, bids.items())), tuple(heapq.nsmallest(n, asks.items()))


def book_hash(bids: dict[float, float], asks: dict[float, float]) -> str:
    """Huella del libro completo (para comparar el del recolector con el reconstruido)."""
    h = hashlib.blake2b(digest_size=12)
    for side in (sorted(bids.items()), sorted(asks.items())):
        h.update(struct.pack(f"<{2 * len(side)}d", *(x for lv in side for x in lv)))
        h.update(b"|")
    return h.hexdigest()


def _describe(exp: Top, loc: Top) -> str:
    for side, a, b in (("bid", exp[0], loc[0]), ("ask", exp[1], loc[1])):
        for i, (x, y) in enumerate(zip_longest(a, b)):
            if x != y:
                return f"{side}#{i}: REST {x} vs local {y}"[:200]
    return ""


class VerifiedBook:
    def __init__(self, top_n: int = TOP_N, ring_max: int = RING_MAX,
                 pending_max: int = PENDING_MAX) -> None:
        self.book = LocalBook()
        self.top_n = top_n
        self.awaiting = True                     # sin libro: se espera un snapshot
        self.pending: deque[Diff] = deque(maxlen=pending_max)
        self.ring: deque[tuple[Diff, Top]] = deque(maxlen=ring_max)
        self.waiting: list[tuple[int, list[Level], list[Level]]] = []   # snapshots por casar
        self.checks: list[Check] = []            # resultados nuevos (los vacía quien los lee)
        self.reset: str | None = None            # «sync»|«divergencia» si el libro se rehízo
        self.pending_dropped = 0

    # --- diffs ---------------------------------------------------------------
    def on_diff(self, d: Diff) -> str:
        """«buffered» (esperando snapshot) | «ok» | «stale» | «gap» (libro perdido)."""
        if self.awaiting:
            if len(self.pending) == self.pending.maxlen:
                self.pending_dropped += 1
            self.pending.append(d)
            return "buffered"
        res = self.book.apply(d.first, d.last, d.prev, d.bids, d.asks)
        if res == "ok":
            self._remember(d)
            self._resolve_waiting(d)
        elif res == "gap":
            self._lost(d)
        return res

    def _remember(self, d: Diff) -> None:
        self.ring.append((d, top_of(self.book.bids, self.book.asks, self.top_n)))

    def _lost(self, d: Diff) -> None:
        self.awaiting = True
        self.ring.clear()
        for snap_id, _, _ in self.waiting:
            self.checks.append(Check(snap_id, -1, False, False, 0, "libro perdido antes de casar"))
        self.waiting.clear()
        self.pending.clear()
        self.pending.append(d)

    # --- snapshots -----------------------------------------------------------
    def on_snapshot(self, last_id: int, bids, asks) -> str:
        """«synced» | «stale_snapshot» (más viejo que lo acumulado) | «waiting» | «checked»."""
        bids = [(float(p), float(q)) for p, q in bids]
        asks = [(float(p), float(q)) for p, q in asks]
        if self.awaiting:
            return self._sync(last_id, bids, asks)
        if not self.book.synced or self.book.last_u is None or last_id > self.book.last_u:
            self.waiting.append((last_id, bids, asks))
            return "waiting"
        for i in range(len(self.ring) - 1, -1, -1):
            d = self.ring[i][0]
            if d.first <= last_id <= d.last:
                self._compare(i, last_id, bids, asks)
                return "checked"
            if d.last < last_id:
                break
        self.checks.append(Check(last_id, -1, False, False, 0, "snapshot fuera de la ventana"))
        return "checked"

    def _sync(self, last_id: int, bids: list[Level], asks: list[Level]) -> str:
        self.book.load_snapshot(last_id, bids, asks)
        pend = list(self.pending)
        self.pending.clear()
        self.awaiting = False
        for i, d in enumerate(pend):
            res = self.book.apply(d.first, d.last, d.prev, d.bids, d.asks)
            if res == "ok":
                self._remember(d)
            elif res == "gap":                   # el snapshot es más viejo que lo acumulado
                self.awaiting = True
                self.ring.clear()
                self.pending.extend(pend[i:])
                return "stale_snapshot"
        self.reset = "sync"
        return "synced"

    def _resolve_waiting(self, d: Diff) -> None:
        keep = []
        for snap_id, bids, asks in self.waiting:
            if snap_id > d.last:
                keep.append((snap_id, bids, asks))
            elif d.first <= snap_id:
                self._compare(len(self.ring) - 1, snap_id, bids, asks)
            else:
                self.checks.append(Check(snap_id, -1, False, False, 0,
                                         "el libro sincronizó después del snapshot"))
        self.waiting = keep

    def _compare(self, i: int, snap_id: int, bids: list[Level], asks: list[Level]) -> None:
        d, local = self.ring[i]
        exp_b, exp_a = dict(bids), dict(asks)
        for side, lv in ((exp_b, d.bids), (exp_a, d.asks)):
            for p, q in lv:
                if q == 0:
                    side.pop(p, None)
                else:
                    side[p] = q
        exp_b = {p: q for p, q in exp_b.items() if q > 0}
        exp_a = {p: q for p, q in exp_a.items() if q > 0}
        exp = top_of(exp_b, exp_a, self.top_n)
        n_diff = sum(x != y for a, b in zip(exp, local, strict=True)
                     for x, y in zip_longest(a, b))
        self.checks.append(Check(snap_id, d.last, True, n_diff == 0, n_diff,
                                 _describe(exp, local)))
        if n_diff:
            self._rebuild(i, exp_b, exp_a)

    def _rebuild(self, i: int, bids: dict[float, float], asks: dict[float, float]) -> None:
        """Libro = snapshot ⊕ diff `i`, y encima los diffs posteriores ya aplicados."""
        ring = list(self.ring)
        d, later = ring[i][0], [x for x, _ in ring[i + 1:]]
        old = self.book
        self.book = LocalBook(bids=bids, asks=asks, last_id=d.last, last_u=d.last, synced=True,
                              ghosts_pruned=old.ghosts_pruned)
        self.ring = deque(ring[:i], maxlen=self.ring.maxlen)
        self._remember(d)
        self.reset = "divergencia"
        for x in later:
            res = self.book.apply(x.first, x.last, x.prev, x.bids, x.asks)
            if res != "ok":                      # no debería: esos diffs ya encadenaban
                self._lost(x)
                return
            self._remember(x)
