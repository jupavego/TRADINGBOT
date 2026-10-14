"""Primitivas comunes de la biblioteca de indicadores (T34). Puras, sin look-ahead.

Convenciones (válidas para todo `eim.indicators`):
- Entradas: arreglos 1D (cualquier secuencia numérica), más antiguo → más reciente.
- Salida: `np.ndarray` float64 del mismo largo; NaN donde no hay datos suficientes.
- Ventanas móviles: si la ventana contiene un NaN, la salida es NaN; ventana > datos → todo NaN.
- Filtros recursivos (EMA, Wilder): arrancan en el primer dato válido; un NaN interior
  deja NaN en ese punto y conserva el estado (no se inventa el dato faltante).
- Divisiones por cero (rango 0, volumen 0) → NaN, salvo que la función declare otra cosa.
- El valor en `t` usa solo datos ≤ `t` (verificado por test de truncado).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

ArrayLike = Sequence[float] | np.ndarray


def arr(x: ArrayLike) -> np.ndarray:
    """Copia float64 1D."""
    a = np.array(x, dtype=float)
    if a.ndim != 1:
        raise ValueError("se esperaba un arreglo 1D")
    return a


def _check_n(n: int) -> None:
    if int(n) != n or n < 1:
        raise ValueError(f"ventana inválida: {n}")


def nan_like(x: np.ndarray) -> np.ndarray:
    return np.full(len(x), np.nan)


def windows(x: np.ndarray, n: int) -> np.ndarray | None:
    """Vista (len-n+1, n) de ventanas; None si n > len."""
    _check_n(n)
    return None if n > len(x) else sliding_window_view(x, n)


def _rolling(x: ArrayLike, n: int, fn) -> np.ndarray:
    a = arr(x)
    out = nan_like(a)
    w = windows(a, n)
    if w is not None:
        out[n - 1:] = fn(w)
    return out


def sma(x: ArrayLike, n: int) -> np.ndarray:
    """Media móvil simple."""
    return _rolling(x, n, lambda w: w.mean(axis=1))


def rolling_sum(x: ArrayLike, n: int) -> np.ndarray:
    return _rolling(x, n, lambda w: w.sum(axis=1))


def rolling_max(x: ArrayLike, n: int) -> np.ndarray:
    return _rolling(x, n, lambda w: w.max(axis=1))


def rolling_min(x: ArrayLike, n: int) -> np.ndarray:
    return _rolling(x, n, lambda w: w.min(axis=1))


def rolling_std(x: ArrayLike, n: int, ddof: int = 0) -> np.ndarray:
    """Desviación estándar móvil (poblacional por defecto, como TA-Lib/Binance BOLL)."""
    return _rolling(x, n, lambda w: w.std(axis=1, ddof=ddof))


def rolling_mad(x: ArrayLike, n: int) -> np.ndarray:
    """Desviación media absoluta respecto de la media de la ventana (CCI)."""
    return _rolling(x, n, lambda w: np.abs(w - w.mean(axis=1, keepdims=True)).mean(axis=1))


def wma(x: ArrayLike, n: int) -> np.ndarray:
    """Media ponderada lineal (peso n para el dato más reciente)."""
    k = np.arange(1, n + 1, dtype=float)
    return _rolling(x, n, lambda w: w @ k / k.sum())


def shift(x: ArrayLike, k: int = 1) -> np.ndarray:
    """x[t-k] (k ≥ 0); los primeros k puntos quedan NaN."""
    a = arr(x)
    out = nan_like(a)
    if k == 0:
        return a
    if k < len(a):
        out[k:] = a[:-k]
    return out


def recursive(x: ArrayLike, alpha: float, seed: float | None = None,
              seed_at: int | None = None) -> np.ndarray:
    """y_t = y_{t-1} + alpha·(x_t − y_{t-1}).

    Sin `seed`: arranca con el primer dato válido (pandas `ewm(adjust=False)`).
    Con `seed` y `seed_at`: y[seed_at] = seed y la recursión sigue desde seed_at+1.
    Con `seed` sin `seed_at`: estado previo = seed antes del primer dato válido.
    """
    a = arr(x)
    out = nan_like(a)
    valid = np.flatnonzero(~np.isnan(a))
    if len(valid) == 0:
        return out
    if seed_at is not None:
        start, y = seed_at, seed
        out[start] = y
        start += 1
    elif seed is not None:
        start, y = int(valid[0]), seed
    else:
        start, y = int(valid[0]) + 1, a[valid[0]]
        out[valid[0]] = y
    for i in range(start, len(a)):
        xi = a[i]
        if xi != xi:  # NaN: hueco, se conserva el estado
            continue
        y = y + alpha * (xi - y)
        out[i] = y
    return out


def ema(x: ArrayLike, n: int, seed: str = "first") -> np.ndarray:
    """EMA con alpha = 2/(n+1).

    seed="first": arranca en el primer dato (pandas `ewm(span=n, adjust=False)`; FRM, Binance).
    seed="sma": primer valor = SMA de los n primeros datos válidos (TA-Lib).
    """
    _check_n(n)
    return _seeded(x, 2.0 / (n + 1), n, seed)


def rma(x: ArrayLike, n: int, seed: str = "sma") -> np.ndarray:
    """Media de Wilder (alpha = 1/n), sembrada con la SMA de los n primeros datos (TA-Lib)."""
    _check_n(n)
    return _seeded(x, 1.0 / n, n, seed)


def _seeded(x: ArrayLike, alpha: float, n: int, seed: str) -> np.ndarray:
    a = arr(x)
    if seed == "first":
        return recursive(a, alpha)
    if seed != "sma":
        raise ValueError(f"seed desconocida: {seed}")
    valid = np.flatnonzero(~np.isnan(a))
    if len(valid) < n:
        return nan_like(a)
    first = int(valid[0])
    head = a[first:first + n]
    if np.isnan(head).any():  # la siembra exige n datos contiguos
        return nan_like(a)
    return recursive(a, alpha, seed=float(head.mean()), seed_at=first + n - 1)


def div(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    """num/den con den == 0 → NaN (sin avisos)."""
    num, den = np.asarray(num, float), np.asarray(den, float)
    out = np.full(np.broadcast(num, den).shape, np.nan)
    np.divide(num, den, out=out, where=(den != 0) & ~np.isnan(den))
    return out
