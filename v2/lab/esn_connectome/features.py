"""Entradas y objetivo del laboratorio, todo causal.

Entrada en t (tras el cierre de la vela t): retorno estandarizado por σ previa, log de σ relativa
a su media lenta, rango relativo y volumen relativo. Objetivo desde el origen t:
`y_t = log(c_{t+h}/c_t) / (σ_t·√h)` (retorno terminal en unidades de volatilidad).
"""

from __future__ import annotations

import numpy as np

LAMBDA = 0.94


def ewma_sigma(ret: np.ndarray, lam: float = LAMBDA) -> np.ndarray:
    """σ_t con información hasta t inclusive (sirve para estandarizar r_{t+1})."""
    var = np.empty(len(ret))
    v = float(np.var(ret[:50])) or 1e-8
    for i, r in enumerate(ret):
        v = lam * v + (1 - lam) * r * r
        var[i] = v
    return np.sqrt(np.maximum(var, 1e-12))


def _ewma(x: np.ndarray, lam: float) -> np.ndarray:
    out = np.empty(len(x))
    m = float(x[0])
    for i, v in enumerate(x):
        m = lam * m + (1 - lam) * v
        out[i] = m
    return out


def build(ohlcv: np.ndarray, horizon: int) -> dict[str, np.ndarray]:
    """`ohlcv (T, 5)` → entradas `u (T, 4)`, σ, retornos terminales `R` y objetivo `y`.

    Los índices se alinean con las velas; `R`/`y` son NaN donde el futuro no existe.
    """
    o, h, lo, c, v = (ohlcv[:, i] for i in range(5))
    ret = np.zeros(len(c))
    ret[1:] = np.diff(np.log(c))
    sig = ewma_sigma(ret)
    prev = np.concatenate([[sig[0]], sig[:-1]])
    z = np.clip(ret / prev, -6, 6)
    lsig = np.log(sig / _ewma(sig, 0.995))
    rng = np.clip(np.log(h / lo) / sig, 0, 12) / 3
    lv = np.log1p(v)
    vol = np.clip(lv - _ewma(lv, 0.98), -4, 4)
    u = np.stack([z / 2, lsig, rng, vol / 2], axis=1)
    big_r = np.full(len(c), np.nan)
    big_r[:-horizon] = np.log(c[horizon:] / c[:-horizon])
    y = big_r / (sig * np.sqrt(horizon))
    return {"u": u, "sigma": sig, "R": big_r, "y": y, "close": c, "open": o}


def lagged(u: np.ndarray, lags: int) -> np.ndarray:
    """Matriz de rezagos `(T, d·lags)` (rellena con 0 al inicio) para la línea base lineal."""
    t, d = u.shape
    out = np.zeros((t, d * lags))
    for k in range(lags):
        out[k:, k * d : (k + 1) * d] = u[: t - k]
    return out
