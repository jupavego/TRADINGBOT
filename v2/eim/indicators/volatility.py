"""Familia volatilidad: rango verdadero, ATR, Bandas de Bollinger (BOLL)."""

from __future__ import annotations

import numpy as np

from eim.indicators._core import ArrayLike, arr, rma, rolling_std, shift, sma


def true_range(high: ArrayLike, low: ArrayLike, close: ArrayLike) -> np.ndarray:
    """TR = max(h−l, |h−c₋₁|, |l−c₋₁|); en la primera vela TR = h−l."""
    h, lo, c = arr(high), arr(low), arr(close)
    pc = shift(c, 1)
    tr = np.fmax(h - lo, np.fmax(np.abs(h - pc), np.abs(lo - pc)))
    if len(tr):
        tr[0] = h[0] - lo[0]
    return tr


def atr(high: ArrayLike, low: ArrayLike, close: ArrayLike, n: int = 14,
        smoothing: str = "wilder") -> np.ndarray:
    """ATR. smoothing="wilder" (TA-Lib, sembrado con SMA) o "sma" (media simple del TR)."""
    tr = true_range(high, low, close)
    if smoothing == "sma":
        return sma(tr, n)
    if smoothing != "wilder":
        raise ValueError(f"smoothing desconocido: {smoothing}")
    if not len(tr):
        return tr
    # TA-Lib descarta el TR de la primera vela (no tiene cierre previo)
    return np.concatenate([[np.nan], rma(tr[1:], n)])


def boll(close: ArrayLike, n: int = 20, k: float = 2.0) -> dict[str, np.ndarray]:
    """Bollinger: medio = SMA(n); bandas = medio ± k·σ poblacional (ddof=0)."""
    c = arr(close)
    mid = sma(c, n)
    sd = rolling_std(c, n, ddof=0)
    return {"up": mid + k * sd, "mb": mid, "dn": mid - k * sd}
