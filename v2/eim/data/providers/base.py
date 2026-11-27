"""Interfaz común de proveedores de datos, partida por capacidades (T90).

Hasta T89 había un único `Provider` con velas, funding e interés abierto: un perpetuo de
Binance. Una acción no tiene funding y una curva no tiene velas, así que cada capacidad es
ahora un protocolo pequeño y un proveedor cumple los que de verdad tiene. `Provider` sigue
existiendo con el mismo significado de siempre (velas + funding + interés abierto) y
`BinanceFutures` lo cumple sin un solo cambio de comportamiento.

Cada proveedor declara además, en `meta` (`eim/data/providers/meta.py`), su nivel de
cobertura (1/2/3), su retraso, sus límites y su licencia. Quien escribe en el almacén con
`eim/data/series.py` deja esa ficha junto a cada serie.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from eim.core import Candle


@runtime_checkable
class CandleProvider(Protocol):
    """Velas OHLCV. Todo método devuelve datos cerrados, ordenados por tiempo."""

    name: str

    def klines(self, symbol: str, timeframe: str, start: int, end: int) -> list[Candle]:
        """Velas cuyo `t` (apertura) está en [start, end) ms; solo velas cerradas."""
        ...


@runtime_checkable
class FundingProvider(Protocol):
    """Tasas de financiación de un perpetuo."""

    name: str

    def funding_rates(self, symbol: str, start: int, end: int) -> list[tuple[int, float]]:
        """(t, tasa) de funding con t en [start, end)."""
        ...


@runtime_checkable
class OpenInterestProvider(Protocol):
    """Interés abierto de un derivado."""

    name: str

    def open_interest(
        self, symbol: str, timeframe: str, start: int, end: int
    ) -> list[tuple[int, float]]:
        """(t, open interest) con t en [start, end)."""
        ...


@runtime_checkable
class QuoteProvider(Protocol):
    """Mejor compra/venta: (t, bid, ask, bid_size, ask_size); tamaños None si no los da."""

    name: str

    def quotes(self, symbol: str, start: int, end: int) -> list[tuple]:
        ...


@runtime_checkable
class CorporateActionsProvider(Protocol):
    """Eventos corporativos: (t de la fecha ex, split, dividendo); el que no aplica, None.

    `split` = acciones nuevas por cada vieja (4.0 en un 4 por 1); `dividendo` en efectivo por
    acción, en la moneda de cotización.
    """

    name: str

    def corporate_actions(self, symbol: str, start: int, end: int) -> list[tuple]:
        ...


@runtime_checkable
class FundamentalsProvider(Protocol):
    """Fundamentales por campo: (t de publicación, valor). Point-in-time: el `t` es cuándo se
    supo, no el periodo al que se refiere."""

    name: str

    def fundamentals(self, symbol: str, field: str, start: int, end: int
                     ) -> list[tuple[int, float]]:
        ...


@runtime_checkable
class CurveProvider(Protocol):
    """Curva por plazo (`10Y`, `3M`…): (t, valor)."""

    name: str

    def curve(self, curve_id: str, tenor: str, start: int, end: int) -> list[tuple[int, float]]:
        ...


@runtime_checkable
class Provider(CandleProvider, FundingProvider, OpenInterestProvider, Protocol):
    """Fuente de un perpetuo: velas, funding e interés abierto (el contrato de siempre)."""


#: Capacidad → protocolo, en el orden en que se informan.
CAPABILITIES: dict[str, type] = {
    "candles": CandleProvider,
    "funding": FundingProvider,
    "open_interest": OpenInterestProvider,
    "quotes": QuoteProvider,
    "corporate_actions": CorporateActionsProvider,
    "fundamentals": FundamentalsProvider,
    "curve": CurveProvider,
}


def capabilities(provider: object) -> tuple[str, ...]:
    """Las capacidades que el proveedor cumple de verdad (por sus métodos, no por su nombre)."""
    return tuple(k for k, proto in CAPABILITIES.items() if isinstance(provider, proto))
