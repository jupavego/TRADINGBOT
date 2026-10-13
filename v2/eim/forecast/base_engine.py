"""Motor base: volatilidad condicional (GARCH ligero) + bootstrap de formas de vela.

Cada vela histórica se normaliza por la volatilidad vigente en ese momento (EWMA retrasada):
hueco de apertura, retorno de cierre y mechas, todo en unidades de σ. Una trayectoria remuestrea
estas formas conjuntamente (conserva la relación cuerpo/mechas) y las reescala con una σ que
evoluciona por GARCH(1,1) con varianza objetivo. La deriva es un parámetro; por defecto 0.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from eim.core import MarketSnapshot
from eim.forecast.engine import check_horizon


@dataclass(frozen=True)
class BaseParams:
    """Parámetros del motor base (calibrados contra cobertura en `eval.py`)."""

    ewma_lambda: float = 0.94
    garch_alpha: float = 0.07
    garch_beta: float = 0.91
    drift: float = 0.0  # retorno log esperado por vela
    lookback: int = 1500  # velas históricas usadas para el bootstrap
    min_candles: int = 100
    seed: int | None = 0


def _log_returns(close: np.ndarray) -> np.ndarray:
    return np.diff(np.log(close))


def _ewma_sigma(ret: np.ndarray, lam: float) -> np.ndarray:
    """σ de cada paso condicionada solo a retornos anteriores (σ[i] no ve ret[i])."""
    var = np.empty(len(ret) + 1)
    var[0] = float(np.var(ret[: min(len(ret), 50)])) or 1e-8
    for i, r in enumerate(ret):
        var[i + 1] = lam * var[i] + (1 - lam) * r * r
    return np.sqrt(var[:-1]), np.sqrt(var[-1])


class BaseEngine:
    """Motor estadístico de línea base."""

    name = "base"

    def __init__(self, params: BaseParams | None = None) -> None:
        self.params = params or BaseParams()

    def sample(self, snapshot: MarketSnapshot, horizon: int, n: int = 200) -> np.ndarray:
        check_horizon(horizon)
        p = self.params
        candles = snapshot.candles[-p.lookback :]
        if len(candles) < p.min_candles:
            raise ValueError(f"se requieren ≥{p.min_candles} velas, hay {len(candles)}")
        a = np.array([[c.o, c.h, c.l, c.c] for c in candles], dtype=float)
        o, h, lo, c = a[1:, 0], a[1:, 1], a[1:, 2], a[1:, 3]
        pc = a[:-1, 3]
        ret = _log_returns(a[:, 3])
        sig, sigma_next = _ewma_sigma(ret, p.ewma_lambda)
        sig = np.maximum(sig, 1e-6)
        gap = np.log(o / pc) / sig
        z = ret / sig
        z = z - z.mean()  # sin deriva implícita en la muestra
        scale = sig * pc
        up = (h - np.maximum(o, c)) / scale
        dn = (np.minimum(o, c) - lo) / scale
        shapes = np.stack([gap, z, up, dn], axis=1)

        rng = np.random.default_rng(p.seed)
        idx = rng.integers(0, len(shapes), size=(n, horizon))
        s = shapes[idx]  # (n, horizon, 4)

        long_var = float(np.var(ret))
        omega = long_var * (1 - p.garch_alpha - p.garch_beta)
        var = np.full(n, sigma_next**2)
        price = np.full(n, a[-1, 3])
        out = np.empty((n, horizon, 4))
        for t in range(horizon):
            sg = np.sqrt(var)
            op = price * np.exp(s[:, t, 0] * sg)
            cl = price * np.exp(p.drift + s[:, t, 1] * sg)
            body_hi, body_lo = np.maximum(op, cl), np.minimum(op, cl)
            hi = body_hi + s[:, t, 2] * sg * price
            lw = np.maximum(body_lo - s[:, t, 3] * sg * price, body_lo * 1e-3)
            out[:, t] = np.stack([op, hi, lw, cl], axis=1)
            r = np.log(cl / price)
            var = omega + p.garch_alpha * r * r + p.garch_beta * var
            price = cl
        return out
