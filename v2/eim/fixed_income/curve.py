"""Curva de tipos: Nelson–Siegel, Svensson, interpolación y *bootstrap* de tipos cero (T100).

Parametrización con τ (en años), la que publica el BCE para su curva AAA del euro:

    NS(m)  = β0 + β1·L1(m/τ1) + β2·L2(m/τ1)
    SV(m)  = NS(m) + β3·L2(m/τ2)
    L1(x) = (1 − e^−x)/x      L2(x) = L1(x) − e^−x

β0 es el nivel (el tipo a plazo infinito), β0+β1 el tipo a plazo cero, β1 la pendiente (con
el signo cambiado) y β2 la curvatura. Diebold–Li escriben λ = 1/τ con m en meses.

El ajuste fija τ en una rejilla y resuelve las β por mínimos cuadrados lineales: es
determinista, no depende de un punto de partida y da el mismo resultado en los dos equipos.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

TAU_GRID = tuple(round(0.25 * k, 2) for k in range(1, 61))    # 0,25 … 15 años


def _l1(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    out = np.ones_like(x)
    nz = x > 1e-12
    out[nz] = (1.0 - np.exp(-x[nz])) / x[nz]
    return out


def _l2(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    return _l1(x) - np.exp(-x)


def nelson_siegel(m, b0: float, b1: float, b2: float, tau: float):
    """Tipo de la curva NS a plazo `m` (años; escalar o vector)."""
    x = np.asarray(m, dtype=float) / tau
    y = b0 + b1 * _l1(x) + b2 * _l2(x)
    return float(y) if np.ndim(m) == 0 else y


def svensson(m, b0: float, b1: float, b2: float, b3: float, tau1: float, tau2: float):
    """Tipo de la curva de Svensson a plazo `m` (años; escalar o vector)."""
    mm = np.asarray(m, dtype=float)
    y = np.asarray(nelson_siegel(mm, b0, b1, b2, tau1)) + b3 * _l2(mm / tau2)
    return float(y) if np.ndim(m) == 0 else y


@dataclass(frozen=True)
class CurveFit:
    """Resultado de un ajuste: parámetros, error y la función de la curva."""

    model: str                 # "nelson_siegel" | "svensson"
    params: dict[str, float]
    rmse: float                # en las unidades de los tipos de entrada
    max_abs_error: float
    n_points: int

    def __call__(self, m):
        p = self.params
        if self.model == "svensson":
            return svensson(m, p["b0"], p["b1"], p["b2"], p["b3"], p["tau1"], p["tau2"])
        return nelson_siegel(m, p["b0"], p["b1"], p["b2"], p["tau1"])

    @property
    def level(self) -> float:
        return self.params["b0"]

    @property
    def slope(self) -> float:
        """Largo menos corto (β0 − (β0+β1) = −β1): positiva = curva normal."""
        return -self.params["b1"]

    @property
    def curvature(self) -> float:
        return self.params["b2"]


def _ols(cols: list[np.ndarray], y: np.ndarray) -> tuple[np.ndarray, float, float]:
    x = np.column_stack(cols)
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    err = y - x @ beta
    return beta, float(np.sqrt(np.mean(err ** 2))), float(np.max(np.abs(err)))


def _check(m: Sequence[float], y: Sequence[float], k: int) -> tuple[np.ndarray, np.ndarray]:
    mm, yy = np.asarray(m, dtype=float), np.asarray(y, dtype=float)
    if mm.shape != yy.shape or mm.ndim != 1:
        raise ValueError("plazos y tipos deben ser vectores de igual longitud")
    if np.any(mm <= 0) or not np.all(np.isfinite(yy)):
        raise ValueError("plazos > 0 y tipos finitos")
    if len(mm) < k:
        raise ValueError(f"hacen falta al menos {k} puntos para este modelo")
    return mm, yy


def fit_nelson_siegel(m: Sequence[float], y: Sequence[float],
                      taus: Sequence[float] = TAU_GRID) -> CurveFit:
    """Mejor NS por mínimos cuadrados (τ en rejilla, β lineales)."""
    mm, yy = _check(m, y, 4)
    best = None
    for tau in taus:
        x = mm / tau
        beta, rmse, mx = _ols([np.ones_like(mm), _l1(x), _l2(x)], yy)
        if best is None or rmse < best[1] - 1e-15:
            best = (beta, rmse, mx, tau)
    beta, rmse, mx, tau = best
    return CurveFit("nelson_siegel", {"b0": float(beta[0]), "b1": float(beta[1]),
                                      "b2": float(beta[2]), "tau1": float(tau)},
                    rmse, mx, len(mm))


def fit_svensson(m: Sequence[float], y: Sequence[float],
                 taus: Sequence[float] = TAU_GRID) -> CurveFit:
    """Mejor Svensson (τ1 < τ2 en rejilla, β lineales). Necesita ≥ 6 puntos."""
    mm, yy = _check(m, y, 6)
    best = None
    for i, t1 in enumerate(taus):
        x1 = mm / t1
        base = [np.ones_like(mm), _l1(x1), _l2(x1)]
        for t2 in taus[i + 1:]:
            beta, rmse, mx = _ols([*base, _l2(mm / t2)], yy)
            if best is None or rmse < best[1] - 1e-15:
                best = (beta, rmse, mx, t1, t2)
    beta, rmse, mx, t1, t2 = best
    keys = ("b0", "b1", "b2", "b3")
    params = {k: float(v) for k, v in zip(keys, beta, strict=True)}
    params.update(tau1=float(t1), tau2=float(t2))
    return CurveFit("svensson", params, rmse, mx, len(mm))


def linear(m: Sequence[float], y: Sequence[float]) -> Callable[[float], float]:
    """Interpolación lineal con extremos planos (lo más simple que no inventa forma)."""
    mm, yy = np.asarray(m, dtype=float), np.asarray(y, dtype=float)
    order = np.argsort(mm)
    mm, yy = mm[order], yy[order]
    return lambda t: float(np.interp(t, mm, yy))


def bootstrap_bonds(bonds: Sequence[tuple[float, float, float, int]],
                    face: float = 100.0) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Tipos cero continuos desde bonos ordenados por vencimiento.

    Cada bono es `(vencimiento, cupón anual en tanto por uno, precio sucio, frecuencia)`.
    Los cupones intermedios se descuentan con la curva ya obtenida (interpolación lineal en el
    tipo cero), y el último flujo despeja el tipo de su plazo: el método del manual.
    """
    ts: list[float] = []
    zs: list[float] = []
    for mat, cpn, px, freq in sorted(bonds):
        c = face * cpn / freq
        k = math.ceil(mat * freq - 1e-9)
        pv = 0.0
        for t in ([mat - j / freq for j in range(k - 1, 0, -1)] if c > 0 else []):
            if not ts:
                raise ValueError(f"cupón en {t} años sin tipo previo para descontarlo")
            pv += c * math.exp(-float(np.interp(t, ts, zs)) * t)
        rest = px - pv
        if rest <= 0:
            raise ValueError(f"precio incoherente en el plazo {mat}")
        ts.append(float(mat))
        zs.append(-math.log(rest / (c + face)) / mat)
    return tuple(ts), tuple(zs)


def par_to_zero(tenors: Sequence[float], par: Sequence[float], freq: int = 2,
                horizon: float | None = None) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Tipos cero continuos desde una curva **par** (rendimientos equivalentes de bono, tanto
    por uno), como la del Tesoro de EE. UU.

    Los plazos de hasta un periodo se tratan como cupón cero (letras); a partir de ahí se
    interpola linealmente la curva par en la rejilla de cupones y se despeja cada factor de
    descuento. Devuelve (plazos de la rejilla, tipos cero continuos).
    """
    pt = linear(tenors, par)
    step = 1.0 / freq
    end = horizon if horizon is not None else max(tenors)
    out: dict[float, float] = {}
    for t in sorted(x for x in tenors if x < step - 1e-12):      # letras: cupón cero
        out[float(t)] = (1.0 + pt(t) / freq) ** (-freq * t)
    grid: list[float] = []                                         # factores en k·step
    for k in range(1, int(round(end * freq)) + 1):
        t, c = k * step, pt(k * step) / freq
        df = 1.0 / (1.0 + c) if k == 1 else (1.0 - c * sum(grid)) / (1.0 + c)
        grid.append(df)
        out[round(t, 12)] = df
    ts = tuple(sorted(out))
    return ts, tuple(-math.log(out[t]) / t for t in ts)


def forward_rate(zero: Callable[[float], float], t1: float, t2: float) -> float:
    """Tipo a plazo continuo entre `t1` y `t2` implícito en la curva cero."""
    if not t2 > t1 >= 0:
        raise ValueError("hace falta 0 ≤ t1 < t2")
    z1 = zero(t1) * t1 if t1 > 0 else 0.0
    return (zero(t2) * t2 - z1) / (t2 - t1)
