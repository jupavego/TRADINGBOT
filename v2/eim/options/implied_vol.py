"""Volatilidad implícita de una opción europea (T100).

Se comprueban antes las cotas de no arbitraje: un precio por debajo del valor intrínseco
descontado o por encima del subyacente no tiene volatilidad implícita, y decirlo es mejor que
devolver un número que el solver se inventó en el borde del intervalo (regla de CLAUDE.md).
"""

from __future__ import annotations

from scipy.optimize import brentq

from eim.options.black_scholes import CALL, bounds, price

SIGMA_MIN, SIGMA_MAX = 1e-4, 10.0


class NoImpliedVol(ValueError):
    """El precio no admite volatilidad implícita (fuera de cotas o sin valor temporal)."""


def implied_vol(px: float, s: float, k: float, t: float, r: float, kind: str = CALL,
                b: float | None = None, tol: float = 1e-10) -> float:
    """σ que reproduce `px` con Black–Scholes generalizado. Levanta `NoImpliedVol` con motivo."""
    if t <= 0:
        raise NoImpliedVol("opción vencida: no tiene valor temporal")
    lo, hi = bounds(s, k, t, r, kind, b)
    eps = 1e-12 * max(1.0, s)
    if px <= lo + eps:
        raise NoImpliedVol(f"precio {px:.6g} ≤ cota inferior {lo:.6g}: sin valor temporal")
    if px >= hi - eps:
        raise NoImpliedVol(f"precio {px:.6g} ≥ cota superior {hi:.6g}: imposible")

    def f(sig: float) -> float:
        return price(s, k, t, r, sig, kind, b) - px

    if f(SIGMA_MIN) > 0 or f(SIGMA_MAX) < 0:
        raise NoImpliedVol(f"σ fuera de [{SIGMA_MIN}, {SIGMA_MAX}]")
    return float(brentq(f, SIGMA_MIN, SIGMA_MAX, xtol=tol, maxiter=200))


def implied_vol_black76(px: float, f: float, k: float, t: float, r: float,
                        kind: str = CALL) -> float:
    """Volatilidad implícita de una opción sobre futuro (Black 1976)."""
    return implied_vol(px, f, k, t, r, kind, b=0.0)
