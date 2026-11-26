"""Bono de cupón fijo: flujos, precio ↔ rendimiento, duración, convexidad y DV01 (T100).

Convenciones (las de los manuales de referencia de las pruebas):

- Tiempos en **años** desde la liquidación; importes por `face` de nominal (100 por defecto).
- Rendimiento en tanto por uno. `comp="periodic"` = compuesto `freq` veces al año (el
  «rendimiento equivalente de bono» de EE. UU. es `freq=2`); `comp="continuous"` = continuo.
- Precio **sucio** (con el cupón corrido); `accrued` da el corrido para pasar a limpio.
- Duración en años. Convexidad en años²; con `comp="periodic"` es la convexidad modificada
  (la segunda derivada del precio respecto del rendimiento, dividida por el precio).
"""

from __future__ import annotations

import math
from collections.abc import Callable

from scipy.optimize import brentq

Flows = tuple[tuple[float, ...], tuple[float, ...]]


def cashflows(coupon: float, maturity: float, freq: int = 2, face: float = 100.0) -> Flows:
    """(tiempos, importes) de un bono de cupón `coupon` (anual, tanto por uno) que vence en
    `maturity` años. El primer cupón puede caer antes de un periodo completo (cupón corrido)."""
    if maturity <= 0 or freq <= 0:
        raise ValueError("maturity y freq deben ser > 0")
    step = 1.0 / freq
    n = math.ceil(maturity * freq - 1e-9)
    times = tuple(round(maturity - k * step, 12) for k in range(n - 1, -1, -1))
    cpn = face * coupon / freq
    amounts = tuple(cpn + (face if i == n - 1 else 0.0) for i in range(n))
    return times, amounts


def accrued(coupon: float, maturity: float, freq: int = 2, face: float = 100.0) -> float:
    """Cupón corrido desde el último pago (conteo lineal por fracción de periodo)."""
    step = 1.0 / freq
    to_next = maturity - step * math.floor(maturity / step - 1e-9)
    elapsed = (step - to_next) / step
    return face * coupon / freq * max(elapsed, 0.0)


def _df(t: float, y: float, comp: str, freq: int) -> float:
    if comp == "continuous":
        return math.exp(-y * t)
    if comp == "periodic":
        return (1.0 + y / freq) ** (-freq * t)
    raise ValueError(f"comp desconocido: {comp!r}")


def price(flows: Flows, y: float, comp: str = "periodic", freq: int = 2) -> float:
    """Precio sucio descontando todos los flujos al rendimiento `y`."""
    times, amounts = flows
    return sum(a * _df(t, y, comp, freq) for t, a in zip(times, amounts, strict=True))


def yield_from_price(flows: Flows, dirty: float, comp: str = "periodic", freq: int = 2,
                     lo: float = -0.5, hi: float = 2.0) -> float:
    """Rendimiento que iguala el precio sucio `dirty` (raíz única: el precio es monótono)."""
    if dirty <= 0:
        raise ValueError("el precio debe ser > 0")
    return float(brentq(lambda y: price(flows, y, comp, freq) - dirty, lo, hi, xtol=1e-14))


def macaulay_duration(flows: Flows, y: float, comp: str = "periodic", freq: int = 2) -> float:
    """Media de los tiempos ponderada por el valor presente de cada flujo (años)."""
    times, amounts = flows
    pv = [a * _df(t, y, comp, freq) for t, a in zip(times, amounts, strict=True)]
    return sum(t * v for t, v in zip(times, pv, strict=True)) / sum(pv)


def modified_duration(flows: Flows, y: float, comp: str = "periodic", freq: int = 2) -> float:
    """−(1/P)·dP/dy. Con capitalización continua coincide con la de Macaulay."""
    d = macaulay_duration(flows, y, comp, freq)
    return d if comp == "continuous" else d / (1.0 + y / freq)


def convexity(flows: Flows, y: float, comp: str = "periodic", freq: int = 2) -> float:
    """(1/P)·d²P/dy² (años²)."""
    times, amounts = flows
    p = price(flows, y, comp, freq)
    if comp == "continuous":
        s = sum(a * t * t * math.exp(-y * t) for t, a in zip(times, amounts, strict=True))
        return s / p
    g = 1.0 + y / freq
    s = sum(a * t * (t + 1.0 / freq) * g ** (-freq * t)
            for t, a in zip(times, amounts, strict=True))
    return s / (p * g * g)


def dv01(flows: Flows, y: float, comp: str = "periodic", freq: int = 2) -> float:
    """Cambio de precio (en las unidades de `face`) por −1 pb de rendimiento."""
    return modified_duration(flows, y, comp, freq) * price(flows, y, comp, freq) * 1e-4


def price_change(flows: Flows, y: float, dy: float, comp: str = "periodic",
                 freq: int = 2) -> tuple[float, float]:
    """Aproximación de 2.º orden del cambio relativo de precio ante `dy` y el exacto:
    (−D·dy + ½·C·dy², exacto). Sirve para decir cuándo la duración sola deja de bastar."""
    approx = (-modified_duration(flows, y, comp, freq) * dy
              + 0.5 * convexity(flows, y, comp, freq) * dy * dy)
    p0 = price(flows, y, comp, freq)
    return approx, price(flows, y + dy, comp, freq) / p0 - 1.0


def price_on_curve(flows: Flows, zero: Callable[[float], float]) -> float:
    """Precio descontando cada flujo a su tipo cero continuo `zero(t)` (curva, no un solo
    rendimiento): lo que hace falta para valorar un bono fuera de la par."""
    times, amounts = flows
    return sum(a * math.exp(-zero(t) * t) for t, a in zip(times, amounts, strict=True))


def par_yield(zero: Callable[[float], float], maturity: float, freq: int = 2) -> float:
    """Cupón que deja el bono a la par (precio 100) sobre la curva cero `zero`."""
    times = cashflows(0.0, maturity, freq)[0]
    dfs = [math.exp(-zero(t) * t) for t in times]
    return freq * (1.0 - dfs[-1]) / sum(dfs)

