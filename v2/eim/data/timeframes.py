"""Marcos temporales soportados y su duración en ms."""

from __future__ import annotations

TF_MS: dict[str, int] = {
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
}

# Marcos solo de almacén/histórico: no se exponen en la API ni en la UI (T43: triangular 1 min).
STORE_ONLY_TF_MS: dict[str, int] = {"1m": 60_000}

SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
# Foco actual: lo que los servicios analizan en vivo y lo que muestra la UI. 2026-10-15: solo
# BTCUSDT; 2026-10-21 (decisión del usuario, fase de entrenamiento): vuelve ETHUSDT con historia
# completa (`python -m eim.data.backfill`) y recolectores propios (`servicio_continuo.ps1`).
FOCUS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")


def tf_ms(timeframe: str) -> int:
    """Duración del marco en ms; falla si no está soportado."""
    try:
        return TF_MS[timeframe] if timeframe in TF_MS else STORE_ONLY_TF_MS[timeframe]
    except KeyError:
        raise ValueError(f"marco no soportado: {timeframe!r} (válidos: {list(TF_MS)})") from None
