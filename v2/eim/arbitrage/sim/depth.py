"""Profundidad para el deslizamiento histórico (T43).

No existen libros históricos: se usa el libro REAL capturado en vivo (T38/T39) como perfil
(distancia al medio en pb, tamaño en USD) y se aplica a cada momento del pasado, adelgazado
según el volumen negociado entonces (nunca más grueso que el capturado). Con varias
capturas de un mismo libro se usa la de costo mediano (`DepthModel.rep`), la misma para la
estimación del motor T38 y para lo realizado: así el deslizamiento no crea diferencias.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from eim.core import Book
from eim.core.arbitrage import Side

Levels = tuple[tuple[float, float], ...]  # (pb desde el medio ≥ 0, USD)


@dataclass(frozen=True)
class DepthProfile:
    key: str  # "<mercado>:<símbolo>", p. ej. "spot:BTCUSDT", "usdm:BTCUSDT_Q1"
    t: int  # hora de la captura (ms)
    bids: Levels
    asks: Levels
    source: str

    @classmethod
    def from_book(cls, key: str, book: Book, t: int, usd: float = 1.0) -> DepthProfile | None:
        """`usd` = valor en USD de una unidad de la moneda cotizada (1 en USDT)."""
        if not book.bids or not book.asks:
            return None
        mid = (book.bids[0][0] + book.asks[0][0]) / 2
        if mid <= 0:
            return None
        bids = tuple(((mid - p) / mid * 1e4, q * p * usd) for p, q in book.bids if p > 0 < q)
        asks = tuple(((p - mid) / mid * 1e4, q * p * usd) for p, q in book.asks if p > 0 < q)
        return cls(key=key, t=t, bids=bids, asks=asks, source=book.source)

    def levels(self, side: Side) -> Levels:
        """Lado que consume una orden a mercado: la compra recorre los asks."""
        return self.asks if side == "buy" else self.bids

    def depth_usd(self, side: Side) -> float:
        return sum(u for _, u in self.levels(side))

    def cost(self, notional: float, side: Side, scale: float = 1.0) -> tuple[float, bool]:
        """Deslizamiento en USD frente al medio al ejecutar `notional` USD con los tamaños
        × `scale`, y si el libro visible alcanzó (lo que falta se valora al último nivel)."""
        left, cost, last = notional, 0.0, 0.0
        for bps, usd in self.levels(side):
            take = min(usd * scale, left)
            cost += take * bps / 1e4
            left -= take
            last = bps
            if left <= 1e-9:
                return cost, True
        return cost + max(left, 0.0) * last / 1e4, left <= 1e-9

    def to_book(self, mid: float, scale: float = 1.0, usd: float = 1.0) -> Book:
        """Libro sintético centrado en `mid` (precios en la cotizada) con tamaños × `scale`."""
        def side(levels: Levels, sign: int) -> list[tuple[float, float]]:
            out = []
            for bps, u in levels:
                px = mid * (1 + sign * bps / 1e4)
                out.append((px, u * scale / usd / px))
            return out
        return Book.model_construct(bids=side(self.bids, -1), asks=side(self.asks, 1),
                                    source=f"{self.source} (perfil capturado)")


class DepthModel:
    """Perfiles por clave; `rep` = captura de costo mediano para el nocional de referencia."""

    def __init__(self, profiles: Iterable[DepthProfile], ref_notional: float = 10_000.0) -> None:
        self.by_key: dict[str, list[DepthProfile]] = {}
        for p in profiles:
            self.by_key.setdefault(p.key, []).append(p)
        self._rep: dict[str, DepthProfile] = {}
        for key, ps in self.by_key.items():
            ranked = sorted(ps, key=lambda p: p.cost(ref_notional, "buy")[0]
                            + p.cost(ref_notional, "sell")[0])
            self._rep[key] = ranked[len(ranked) // 2]

    def has(self, key: str) -> bool:
        return key in self._rep

    def rep(self, key: str) -> DepthProfile | None:
        return self._rep.get(key)

    def captures(self, key: str) -> int:
        return len(self.by_key.get(key, []))

    def cost(self, key: str, notional: float, side: Side,
             scale: float = 1.0) -> tuple[float, bool] | None:
        """None si no hay perfil para la clave (el llamador lo declara)."""
        p = self._rep.get(key)
        return None if p is None else p.cost(notional, side, scale)
