"""Datos de mercado para arbitraje (T38): entrada pura de `eim/arbitrage/`.

I/O en `eim/data/arb_market.py`. Libros como `Book` (mejor precio primero); toda pieza
expone su `source` y su cobertura en `sources`/`coverage` con claves
`book:<mercado>:<símbolo>`, `premium:<símbolo>`, `funding:<símbolo>`, `borrow:<activo>`.
"""

from __future__ import annotations

from typing import Literal

from eim.core.arbitrage import MarketKind
from eim.core.market import Book, Frozen

ContractKind = Literal["perpetual", "quarterly"]


class SpotPair(Frozen):
    symbol: str
    base: str
    quote: str


class FuturesContract(Frozen):
    """Contrato de futuros de Binance (USDⓈ-M o USDC-M según `margin`)."""

    symbol: str  # "BTCUSDT", "BTCUSDT_251226", "BTCUSDC"
    base: str
    margin: str  # "USDT" o "USDC"
    kind: ContractKind
    delivery_t: int | None = None  # vencimiento (ms) de los trimestrales

    @property
    def market(self) -> MarketKind:
        return "usdcm" if self.margin == "USDC" else "usdm"


class PremiumInfo(Frozen):
    """`premiumIndex` de un perpetuo: funding previsto para la próxima liquidación."""

    symbol: str
    mark: float
    index: float
    funding_rate: float  # tasa prevista de la próxima liquidación (lastFundingRate)
    next_funding_t: int
    interval_h: float = 8.0
    t: int


class ArbMarket(Frozen):
    """Fotografía de Binance para arbitraje. `borrow_apr` = interés anual (fracción) por
    activo para préstamo spot; vacío si no se configuró (no hay API pública sin clave).
    Lo que no se pudo cargar no aparece en los diccionarios y su motivo queda en `errors`."""

    asof: int
    spot_pairs: list[SpotPair] = []
    contracts: list[FuturesContract] = []
    spot_books: dict[str, Book] = {}
    futures_books: dict[str, Book] = {}
    premium: dict[str, PremiumInfo] = {}
    funding_hist: dict[str, list[tuple[int, float]]] = {}
    borrow_apr: dict[str, float] = {}
    sources: dict[str, str] = {}
    coverage: dict[str, tuple[int, int]] = {}
    errors: dict[str, str] = {}  # misma clave que `coverage`: por qué falta esa pieza

    def perpetual(self, base: str, margin: str = "USDT") -> FuturesContract | None:
        return next((c for c in self.contracts if c.base == base and c.margin == margin
                     and c.kind == "perpetual"), None)

    def quarterlies(self, base: str, margin: str = "USDT") -> list[FuturesContract]:
        out = [c for c in self.contracts if c.base == base and c.margin == margin
               and c.kind == "quarterly" and c.delivery_t and c.delivery_t > self.asof]
        return sorted(out, key=lambda c: c.delivery_t or 0)

    def spot_symbol(self, base: str, quote: str) -> str | None:
        return next((p.symbol for p in self.spot_pairs
                     if p.base == base and p.quote == quote), None)
