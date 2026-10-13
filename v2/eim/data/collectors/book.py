"""Libro L2 local reconstruido desde diffs de Binance Futures (`depth@100ms`).

Protocolo oficial: tras cargar el snapshot REST (`lastUpdateId`), se descartan los eventos con
`u < lastUpdateId`; el primero aplicable cumple `U <= lastUpdateId <= u`; cada evento siguiente
debe encadenar (`pu` == `u` del anterior). Cualquier ruptura marca el libro como desincronizado
y obliga a resincronizar: nunca se sigue aplicando sobre un libro dudoso (niveles fantasma).
Puro: sin red ni disco.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Result = Literal["ok", "stale", "gap", "unsynced"]


@dataclass
class LocalBook:
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    last_id: int = 0  # lastUpdateId del snapshot
    last_u: int | None = None  # `u` del último evento aplicado
    synced: bool = False
    ghosts_pruned: int = 0

    def load_snapshot(self, last_id: int, bids, asks) -> None:
        self.bids = {float(p): float(q) for p, q in bids if float(q) > 0}
        self.asks = {float(p): float(q) for p, q in asks if float(q) > 0}
        self.last_id, self.last_u, self.synced = last_id, None, False

    def desync(self) -> None:
        """Descarta el libro entero (hay que pedir un snapshot nuevo)."""
        self.bids, self.asks, self.last_id, self.last_u, self.synced = {}, {}, 0, None, False

    def apply(self, first: int, last: int, prev: int, bids, asks) -> Result:
        """Aplica un diff (`U`, `u`, `pu`). 'gap' = secuencia rota → libro desincronizado."""
        if not self.last_id:
            return "unsynced"
        if not self.synced:
            if last < self.last_id:
                return "stale"
            if first > self.last_id:  # el snapshot es más viejo que el primer evento
                self.desync()
                return "gap"
            self.synced = True
        elif prev != self.last_u:
            self.desync()
            return "gap"
        for book, levels in ((self.bids, bids), (self.asks, asks)):
            for p, q in levels:
                p, q = float(p), float(q)
                if q == 0:
                    book.pop(p, None)
                else:
                    book[p] = q
        self.last_u = last
        self._uncross(updated_bids=bool(bids), updated_asks=bool(asks))
        return "ok"

    def _uncross(self, updated_bids: bool, updated_asks: bool) -> None:
        """Un libro cruzado delata niveles fantasma: se eliminan los del lado NO actualizado."""
        while self.bids and self.asks:
            bb, ba = max(self.bids), min(self.asks)
            if bb < ba:
                return
            if updated_bids and not updated_asks:
                del self.asks[ba]
            elif updated_asks and not updated_bids:
                del self.bids[bb]
            else:  # ambos lados cambiaron: no se sabe cuál es el viejo → se descartan ambos
                del self.bids[bb]
                del self.asks[ba]
            self.ghosts_pruned += 1

    def top(self, n: int = 10) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        bids = sorted(self.bids.items(), reverse=True)[:n]
        asks = sorted(self.asks.items())[:n]
        return bids, asks
