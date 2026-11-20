"""Volatilidad realizada del mid (T80): RV, variación bipotencia y parte de salto. Puras.

Sobre retornos logarítmicos entre cubos consecutivos (cada retorno usa la fila actual y la
anterior). La RV mide toda la variación; la bipotencia (Barndorff-Nielsen–Shephard) es robusta a
los saltos, así que su diferencia estima la parte de salto. Todo en ventanas hacia atrás.
"""

from __future__ import annotations

import math

import numpy as np

from eim.hft.features.sampling import trailing_sum

MU1 = math.sqrt(2 / math.pi)        # E|Z| de una normal estándar


def log_returns(price: np.ndarray) -> np.ndarray:
    """Retorno logarítmico de cada fila frente a la anterior (la primera es NaN)."""
    p = np.asarray(price, float)
    out = np.full(p.shape[0], np.nan)
    if p.shape[0] > 1:
        out[1:] = np.log(np.maximum(p[1:], 1e-12) / np.maximum(p[:-1], 1e-12))
    return out


def realized_variance(ret: np.ndarray, window: int) -> np.ndarray:
    """Suma de retornos al cuadrado de la ventana (NaN en el calentamiento)."""
    r = np.nan_to_num(np.asarray(ret, float), nan=0.0)
    return trailing_sum(r * r, window)


def bipower(ret: np.ndarray, window: int) -> np.ndarray:
    """Variación bipotencia: (1/μ₁²)·Σ |r_i|·|r_{i−1}| en la ventana."""
    r = np.abs(np.nan_to_num(np.asarray(ret, float), nan=0.0))
    prod = np.zeros(r.shape[0])
    if r.shape[0] > 1:
        prod[1:] = r[1:] * r[:-1]
    return trailing_sum(prod, window) / (MU1 * MU1)


def jump_share(ret: np.ndarray, window: int, eps: float = 1e-18) -> np.ndarray:
    """Parte de la RV que no explica la bipotencia, en [0, 1]: proxy de saltos."""
    rv, bv = realized_variance(ret, window), bipower(ret, window)
    return np.clip((rv - bv) / np.maximum(rv, eps), 0.0, 1.0)


def realized_vol_bps(ret: np.ndarray, window: int) -> np.ndarray:
    """Volatilidad realizada de la ventana en pb (raíz de la RV)."""
    return np.sqrt(np.maximum(realized_variance(ret, window), 0.0)) * 1e4
