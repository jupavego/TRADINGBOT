"""Black–Scholes–Merton generalizado (costo de carry `b`) y sus griegas (T100).

Notación de Haug (*The Complete Guide to Option Pricing Formulas*):

    d1 = [ln(S/K) + (b + σ²/2)·T] / (σ·√T)        d2 = d1 − σ·√T
    call = S·e^{(b−r)T}·N(d1) − K·e^{−rT}·N(d2)
    put  = K·e^{−rT}·N(−d2) − S·e^{(b−r)T}·N(−d1)

`b = r` acción sin dividendos (Black–Scholes 1973) · `b = r − q` con dividendo continuo
(Merton 1973) · `b = 0` opción sobre futuro (Black 1976) · `b = r − r_f` divisa
(Garman–Kohlhagen). Tipos continuos, tiempo en años, σ anual en tanto por uno.

Unidades de las griegas: delta y gamma por unidad de subyacente; vega por 1,00 de σ (÷100 para
un punto); theta por año (÷365 para un día natural); rho por 1,00 de `r` (÷100 para un punto).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

CALL, PUT = "call", "put"


def _n(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _validate(s: float, k: float, t: float, sigma: float, kind: str) -> None:
    if kind not in (CALL, PUT):
        raise ValueError(f"kind debe ser {CALL!r} o {PUT!r}")
    if s <= 0 or k <= 0:
        raise ValueError("subyacente y precio de ejercicio deben ser > 0")
    if t <= 0 or sigma <= 0:
        raise ValueError("plazo y volatilidad deben ser > 0 (al vencimiento: valor intrínseco)")


def d1_d2(s: float, k: float, t: float, r: float, b: float, sigma: float) -> tuple[float, float]:
    v = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + (b + 0.5 * sigma * sigma) * t) / v
    return d1, d1 - v


def price(s: float, k: float, t: float, r: float, sigma: float, kind: str = CALL,
          b: float | None = None) -> float:
    """Precio de la opción europea (`b` por defecto = `r`)."""
    _validate(s, k, t, sigma, kind)
    b = r if b is None else b
    d1, d2 = d1_d2(s, k, t, r, b, sigma)
    fs, fk = s * math.exp((b - r) * t), k * math.exp(-r * t)
    if kind == CALL:
        return fs * _cdf(d1) - fk * _cdf(d2)
    return fk * _cdf(-d2) - fs * _cdf(-d1)


def black76(f: float, k: float, t: float, r: float, sigma: float, kind: str = CALL) -> float:
    """Opción europea sobre un futuro o forward de precio `f` (Black 1976: `b = 0`)."""
    return price(f, k, t, r, sigma, kind, b=0.0)


@dataclass(frozen=True)
class Greeks:
    price: float
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float


def greeks(s: float, k: float, t: float, r: float, sigma: float, kind: str = CALL,
           b: float | None = None, carry_follows_rate: bool | None = None) -> Greeks:
    """Precio y griegas analíticas.

    `rho` es la derivada respecto de `r`. Si el carry se mueve con el tipo (acción: `b = r − q`)
    vale `±T·K·e^{−rT}·N(±d2)`; si el carry es fijo (futuro: `b = 0`) vale `−T·precio`. Por
    defecto se supone que se mueve con el tipo salvo que `b == 0`.
    """
    _validate(s, k, t, sigma, kind)
    b = r if b is None else b
    follows = (b != 0.0) if carry_follows_rate is None else carry_follows_rate
    d1, d2 = d1_d2(s, k, t, r, b, sigma)
    carry = math.exp((b - r) * t)
    disc = math.exp(-r * t)
    sq = math.sqrt(t)
    gamma = carry * _n(d1) / (s * sigma * sq)
    vega = s * carry * _n(d1) * sq
    decay = -s * carry * _n(d1) * sigma / (2.0 * sq)
    if kind == CALL:
        px = s * carry * _cdf(d1) - k * disc * _cdf(d2)
        delta = carry * _cdf(d1)
        theta = decay - (b - r) * s * carry * _cdf(d1) - r * k * disc * _cdf(d2)
        rho = t * k * disc * _cdf(d2) if follows else -t * px
    else:
        px = k * disc * _cdf(-d2) - s * carry * _cdf(-d1)
        delta = carry * (_cdf(d1) - 1.0)
        theta = decay + (b - r) * s * carry * _cdf(-d1) + r * k * disc * _cdf(-d2)
        rho = -t * k * disc * _cdf(-d2) if follows else -t * px
    return Greeks(px, delta, gamma, vega, theta, rho)


def parity_gap(call: float, put: float, s: float, k: float, t: float, r: float,
               b: float | None = None) -> float:
    """Desvío de la paridad put-call: (C − P) − (S·e^{(b−r)T} − K·e^{−rT}). Cero sin arbitraje."""
    b = r if b is None else b
    return (call - put) - (s * math.exp((b - r) * t) - k * math.exp(-r * t))


def bounds(s: float, k: float, t: float, r: float, kind: str = CALL,
           b: float | None = None) -> tuple[float, float]:
    """Cotas de no arbitraje del precio (σ → 0 y σ → ∞)."""
    b = r if b is None else b
    fs, fk = s * math.exp((b - r) * t), k * math.exp(-r * t)
    if kind == CALL:
        return max(fs - fk, 0.0), fs
    return max(fk - fs, 0.0), fk
