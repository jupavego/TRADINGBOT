"""Muestreo y ventanas hacia atrás (T80). Puras: ningún resultado usa una fila posterior.

Dos relojes, como pide la tarea: por **tiempo** (los cubos del panel, `step_ms`) y por
**volumen** (`volume_clock`: un cubo nuevo cada `bucket` unidades negociadas). Las ventanas
(`trailing_*`) devuelven NaN mientras no hay historia suficiente, así que el calentamiento se ve
en los datos y no se cuela en las métricas.
"""

from __future__ import annotations

import numpy as np


def trailing_sum(x: np.ndarray, window: int) -> np.ndarray:
    """Suma de las `window` últimas filas (la actual incluida); NaN en el calentamiento."""
    a = np.asarray(x, float)
    if window < 1:
        raise ValueError("window ≥ 1")
    out = np.full(a.shape[0], np.nan)
    if a.shape[0] < window:
        return out
    c = np.concatenate([[0.0], np.nancumsum(a)])
    out[window - 1:] = c[window:] - c[:a.shape[0] - window + 1]
    return out


def trailing_mean(x: np.ndarray, window: int) -> np.ndarray:
    return trailing_sum(x, window) / window


def trailing_std(x: np.ndarray, window: int, eps: float = 1e-12) -> np.ndarray:
    """Desviación típica poblacional de la ventana hacia atrás."""
    a = np.asarray(x, float)
    m = trailing_mean(a, window)
    m2 = trailing_mean(a * a, window)
    return np.sqrt(np.maximum(m2 - m * m, eps))


def trailing_z(x: np.ndarray, window: int, eps: float = 1e-12) -> np.ndarray:
    """z de la fila actual contra su propia ventana hacia atrás (sin mirar adelante)."""
    a = np.asarray(x, float)
    return (a - trailing_mean(a, window)) / np.maximum(trailing_std(a, window), eps)


def volume_clock(volume: np.ndarray, bucket: float) -> np.ndarray:
    """Índice de cubo de volumen de cada fila: un cubo nuevo cada `bucket` unidades.

    El índice de una fila depende solo del volumen acumulado hasta ella (incluida).
    """
    if bucket <= 0:
        raise ValueError("bucket > 0")
    return np.floor(np.cumsum(np.asarray(volume, float)) / bucket).astype(np.int64)


def bucket_last_rows(idx: np.ndarray) -> np.ndarray:
    """Última fila de cada cubo (índices crecientes): los instantes del reloj de volumen."""
    a = np.asarray(idx)
    if a.size == 0:
        return np.empty(0, dtype=np.int64)
    return np.flatnonzero(np.concatenate([np.diff(a) != 0, [True]]))


def bucket_sums(idx: np.ndarray, x: np.ndarray, n_rows: int) -> np.ndarray:
    """Suma de `x` por cubo, repartida en la última fila de cada cubo (0 en las demás).

    Sirve para pasar una serie del reloj de tiempo al de volumen sin perder nada.
    """
    a = np.asarray(idx)
    out = np.zeros(n_rows)
    last = bucket_last_rows(a)
    sums = np.add.reduceat(np.asarray(x, float), np.concatenate([[0], last[:-1] + 1]))
    out[last] = sums
    return out
