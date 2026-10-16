"""Marcos temporales soportados y su duración en ms."""

from __future__ import annotations

TF_MS: dict[str, int] = {
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
}

SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
# Foco actual (2026-10-15): lo que los servicios analizan en vivo y lo que muestra la UI.
# ETHUSDT sigue en SYMBOLS (la API y el almacén lo admiten), pero no se analiza por defecto.
FOCUS: tuple[str, ...] = ("BTCUSDT",)


def tf_ms(timeframe: str) -> int:
    """Duración del marco en ms; falla si no está soportado."""
    try:
        return TF_MS[timeframe]
    except KeyError:
        raise ValueError(f"marco no soportado: {timeframe!r} (válidos: {list(TF_MS)})") from None
