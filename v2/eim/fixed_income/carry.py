"""Carry y roll-down con la curva quieta (T100).

Qué rinde un bono en un horizonte `h` si la curva **no se mueve**: el tipo que cobra mientras
lo tiene (carry) más lo que gana porque, al acortarse su plazo, se descuenta a un tipo de la
curva distinto (roll-down). Menos lo que cuesta financiarlo (repo/tipo corto). Es la base de
cualquier agente de «carry» y la primera comprobación de si una posición en duración paga su
riesgo.

Para un cupón cero de plazo T con tipos continuos la descomposición es exacta:

    ln(P_h / P_0) = z(T)·h  +  (T − h)·(z(T) − z(T − h))
                    carry        roll-down

y la suma es la integral del tipo a plazo entre T − h y T (lo comprueba una prueba).
Para un bono con cupón se revaloriza con la curva desplazada y se suman los cupones cobrados.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from eim.fixed_income.bond import Flows, price_on_curve


@dataclass(frozen=True)
class CarryRoll:
    """Rendimientos del horizonte en tanto por uno (log para el cupón cero, simple para el
    bono con cupón), sin anualizar."""

    maturity: float
    horizon: float
    carry: float
    rolldown: float
    funding: float           # costo de financiación del horizonte (≥ 0 si el tipo es > 0)

    @property
    def total(self) -> float:
        return self.carry + self.rolldown

    @property
    def excess(self) -> float:
        """Lo que queda tras pagar la financiación: lo que un agente compara con el riesgo."""
        return self.total - self.funding

    def breakeven_bp(self, duration: float) -> float:
        """Subida del tipo (pb) que se come el exceso en el horizonte: exceso / duración."""
        return self.excess / duration * 1e4 if duration > 0 else math.nan


def _check(maturity: float, horizon: float) -> None:
    if not 0 < horizon < maturity:
        raise ValueError("hace falta 0 < horizonte < vencimiento")


def zero_coupon(zero: Callable[[float], float], maturity: float, horizon: float,
                funding_rate: float = 0.0) -> CarryRoll:
    """Carry y roll-down exactos de un cupón cero con la curva cero continua `zero`.
    `funding_rate` es el tipo continuo de financiación del horizonte."""
    _check(maturity, horizon)
    z_t, z_th = zero(maturity), zero(maturity - horizon)
    return CarryRoll(maturity, horizon, carry=z_t * horizon,
                     rolldown=(maturity - horizon) * (z_t - z_th),
                     funding=funding_rate * horizon)


def coupon_bond(zero: Callable[[float], float], flows: Flows, horizon: float,
                funding_rate: float = 0.0) -> CarryRoll:
    """Bono con cupón: precio hoy sobre la curva, precio en `h` con la **misma** curva y los
    plazos acortados, más los cupones cobrados hasta `h` (sin reinvertir).

    Se separa así: carry = (cupones cobrados + revalorización a rendimiento constante) y
    roll-down = el resto de la revalorización (lo que aporta la pendiente de la curva).
    """
    times, amounts = flows
    maturity = max(times)
    _check(maturity, horizon)
    p0 = price_on_curve(flows, zero)
    paid = sum(a for t, a in zip(times, amounts, strict=True) if t <= horizon)
    later = tuple((t - horizon, a) for t, a in zip(times, amounts, strict=True) if t > horizon)
    rest: Flows = (tuple(t for t, _ in later), tuple(a for _, a in later))
    p_h = price_on_curve(rest, zero)
    # Mismo bono revalorizado con una curva plana al rendimiento de hoy: solo el paso del tiempo.
    y = _flat_yield(flows, p0)
    p_h_flat = price_on_curve(rest, lambda _t: y)
    total = (p_h + paid) / p0 - 1.0
    carry = (p_h_flat + paid) / p0 - 1.0
    return CarryRoll(maturity, horizon, carry=carry, rolldown=total - carry,
                     funding=math.exp(funding_rate * horizon) - 1.0)


def _flat_yield(flows: Flows, dirty: float) -> float:
    """Rendimiento continuo único que reproduce `dirty` (bisección: el precio es monótono)."""
    lo, hi = -0.5, 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if price_on_curve(flows, lambda _t, m=mid: m) > dirty:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
