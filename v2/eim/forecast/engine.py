"""Interfaz común de los motores de trayectorias."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from eim.core import MarketSnapshot

MIN_HORIZON = 20
MAX_HORIZON = 30
OHLC = ("o", "h", "l", "c")


@runtime_checkable
class Engine(Protocol):
    """Genera trayectorias OHLC simuladas desde el último cierre del snapshot."""

    name: str

    def sample(self, snapshot: MarketSnapshot, horizon: int, n: int) -> np.ndarray:
        """Devuelve un array `(n, horizon, 4)` con columnas (o, h, l, c)."""
        ...


def check_horizon(horizon: int) -> None:
    if not MIN_HORIZON <= horizon <= MAX_HORIZON:
        raise ValueError(f"horizonte fuera de rango {MIN_HORIZON}..{MAX_HORIZON}: {horizon}")


def valid_candles(paths: np.ndarray) -> bool:
    """True si toda vela cumple h ≥ max(o,c), l ≤ min(o,c) y precios positivos y finitos."""
    o, h, lo, c = (paths[..., i] for i in range(4))
    return bool(
        np.isfinite(paths).all()
        and (lo > 0).all()
        and (h >= np.maximum(o, c)).all()
        and (lo <= np.minimum(o, c)).all()
    )
