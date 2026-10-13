"""Interfaz común de proveedores de datos."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from eim.core import Candle


@runtime_checkable
class Provider(Protocol):
    """Fuente de datos históricos. Todo método devuelve datos cerrados, ordenados por tiempo."""

    name: str

    def klines(self, symbol: str, timeframe: str, start: int, end: int) -> list[Candle]:
        """Velas cuyo `t` (apertura) está en [start, end) ms; solo velas cerradas."""
        ...

    def funding_rates(self, symbol: str, start: int, end: int) -> list[tuple[int, float]]:
        """(t, tasa) de funding con t en [start, end)."""
        ...

    def open_interest(
        self, symbol: str, timeframe: str, start: int, end: int
    ) -> list[tuple[int, float]]:
        """(t, open interest) con t en [start, end)."""
        ...
