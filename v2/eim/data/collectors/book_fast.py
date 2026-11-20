"""Libro L2 con top-N en tiempo constante (T80). Puro: sin red ni disco.

Mismas reglas de secuencia y el mismo podado de fantasmas que `LocalBook` (T23), pero con las
claves de cada lado en una lista ordenada (`bisect`), así que el mejor nivel y el top-N no
cuestan un `max()` ni un `sorted()` del libro entero. `LocalBook` sigue siendo la referencia: la
captura y el conversor se quedan con ella y `tests/data/test_book_fast.py` exige que las dos
coincidan nivel a nivel sobre secuencias aleatorias con huecos y libros cruzados.

Por qué hacía falta: reconstruir el panel de T80 pide el top-5 **después de cada diff**
(≈ 36 000 por hora × 400 horas). Con `LocalBook.top()` (un `sorted()` de ~10 000 niveles) una
hora costaba minutos; así cuesta segundos.
"""

from __future__ import annotations

from bisect import bisect_left, insort
from dataclasses import dataclass, field

from eim.data.collectors.book import Result

Level = tuple[float, float]


@dataclass
class FastBook:
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    last_id: int = 0                 # lastUpdateId del snapshot
    last_u: int | None = None        # `u` del último evento aplicado
    synced: bool = False
    ghosts_pruned: int = 0
    last_pruned: list[tuple[str, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._bk = sorted(self.bids)          # precios de compra, ascendente
        self._ak = sorted(self.asks)          # precios de venta, ascendente

    # --- estado ---------------------------------------------------------------
    def load_snapshot(self, last_id: int, bids, asks) -> None:
        self.bids = {float(p): float(q) for p, q in bids if float(q) > 0}
        self.asks = {float(p): float(q) for p, q in asks if float(q) > 0}
        self._bk, self._ak = sorted(self.bids), sorted(self.asks)
        self.last_id, self.last_u, self.synced = last_id, None, False

    def desync(self) -> None:
        self.bids, self.asks, self._bk, self._ak = {}, {}, [], []
        self.last_id, self.last_u, self.synced = 0, None, False

    @property
    def best_bid(self) -> float | None:
        return self._bk[-1] if self._bk else None

    @property
    def best_ask(self) -> float | None:
        return self._ak[0] if self._ak else None

    def top(self, n: int = 10) -> tuple[list[Level], list[Level]]:
        """(compras de mayor a menor, ventas de menor a mayor), hasta `n` niveles."""
        bids = [(p, self.bids[p]) for p in reversed(self._bk[-n:])] if n else []
        asks = [(p, self.asks[p]) for p in self._ak[:n]] if n else []
        return bids, asks

    # --- diffs ----------------------------------------------------------------
    def apply(self, first: int, last: int, prev: int, bids, asks) -> Result:
        """Aplica un diff (`U`, `u`, `pu`); «gap» = secuencia rota → libro desincronizado."""
        if not self.last_id:
            return "unsynced"
        if not self.synced:
            if last < self.last_id:
                return "stale"
            if first > self.last_id:
                self.desync()
                return "gap"
            self.synced = True
        elif prev != self.last_u:
            self.desync()
            return "gap"
        self.last_pruned = []
        for book, keys, levels in ((self.bids, self._bk, bids), (self.asks, self._ak, asks)):
            for p, q in levels:
                p, q = float(p), float(q)
                if q == 0:
                    if book.pop(p, None) is not None:
                        i = bisect_left(keys, p)
                        if i < len(keys) and keys[i] == p:
                            keys.pop(i)
                elif p not in book:
                    book[p] = q
                    insort(keys, p)
                else:
                    book[p] = q
        self.last_u = last
        self._uncross(updated_bids=bool(bids), updated_asks=bool(asks))
        return "ok"

    def _uncross(self, updated_bids: bool, updated_asks: bool) -> None:
        """Un libro cruzado delata niveles fantasma: se eliminan los del lado NO actualizado."""
        while self._bk and self._ak:
            bb, ba = self._bk[-1], self._ak[0]
            if bb < ba:
                return
            if updated_bids and not updated_asks:
                self._drop_ask(ba)
            elif updated_asks and not updated_bids:
                self._drop_bid(bb)
            else:        # ambos lados cambiaron: no se sabe cuál es el viejo → se descartan ambos
                self._drop_bid(bb)
                self._drop_ask(ba)
            self.ghosts_pruned += 1

    def _drop_bid(self, p: float) -> None:
        del self.bids[p]
        self._bk.pop()
        self.last_pruned.append(("b", p))

    def _drop_ask(self, p: float) -> None:
        del self.asks[p]
        self._ak.pop(0)
        self.last_pruned.append(("a", p))
