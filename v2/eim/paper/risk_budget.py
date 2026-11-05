"""Riesgo presupuestado con costos (T136, entregables 1 y 2).

El bróker simulado dimensiona hoy con la distancia al SL a secas: `qty = riesgo / |entrada − SL|`.
Al tocar el SL inicial no se pierde el riesgo declarado, sino **el riesgo más los costos de ida y
vuelta**, porque las comisiones y el deslizamiento se pagan sobre la cantidad. Medido en el banco
de T131 con la escalera, el costo medio es 0,167 R, así que un perfil que dice arriesgar 0,5 % del
capital arriesga de hecho ≈ 0,58 %. Eso es lo que corrige `budget_distance`.

Aquí vive **una sola** definición del costo en R (`cost_r`), la misma que usa el veto de
`vetoes.py` (tope `max_cost_r`) y la que mide el informe de T136: dos definiciones distintas del
mismo número son la forma más fácil de que el riesgo presupuestado y el veto se contradigan (E11
de §8 de `PLAN/notas/T129_sl_dinamico.md` pide lo mismo para σ).

Puro: sin red, sin disco y sin estado. El interruptor que decide si el tamaño incluye los costos
es `ProfileParams.risk_includes_costs`, **apagado por defecto**: encenderlo cambia el tamaño de
todas las entradas de una corrida en marcha (T31) y es decisión ◆ del usuario.
"""

from __future__ import annotations

import math

# El veto de `vetoes.py` dividía por `(dist / entry) or 1e-9`. Se conserva igual, al dígito, para
# que el tope de costo decida exactamente lo mismo que antes de centralizarlo aquí.
_FLAT = 1e-9


def cost_per_unit(entry: float, est_cost_frac: float) -> float:
    """Costo estimado de ida y vuelta por unidad, en precio."""
    return max(0.0, entry) * max(0.0, est_cost_frac)


def cost_r(entry: float, sl: float, est_cost_frac: float) -> float:
    """Costo de ida y vuelta **en R**: lo que el viaje completo se come del riesgo al SL.

    Con geometría inválida (entrada ≤ 0 o SL en la entrada) devuelve un número enorme, no `inf`,
    para no cambiar el comportamiento del veto que ya existía.
    """
    if entry <= 0 or not math.isfinite(entry) or not math.isfinite(sl):
        return est_cost_frac / _FLAT
    return est_cost_frac / ((abs(entry - sl) / entry) or _FLAT)


def budget_distance(entry: float, sl: float, est_cost_frac: float,
                    with_costs: bool = True) -> float:
    """Distancia que consume el riesgo presupuestado: al SL, más el costo si se incluye.

    `with_costs=False` devuelve la distancia de hoy, para poder medir las dos con el mismo código.
    """
    dist = abs(entry - sl)
    if dist <= 0 or not math.isfinite(dist):
        return 0.0
    return dist + cost_per_unit(entry, est_cost_frac) if with_costs else dist


def qty_for_risk(risk_usd: float, entry: float, sl: float, est_cost_frac: float,
                 with_costs: bool = True) -> float:
    """Cantidad que arriesga `risk_usd` hasta el SL. 0 si la geometría no sirve."""
    d = budget_distance(entry, sl, est_cost_frac, with_costs)
    if d <= 0 or risk_usd <= 0:
        return 0.0
    return risk_usd / d


def loss_at_stop(risk_usd: float, entry: float, sl: float, est_cost_frac: float,
                 with_costs: bool = True) -> float:
    """Lo que se pierde de verdad (USDT) si salta el SL inicial, costos incluidos.

    Con `with_costs=True` sale exactamente `risk_usd`: eso es lo que significa presupuestar el
    riesgo. Con `False` sale `risk_usd · (1 + costo en R)`, que es lo que pasa hoy.
    """
    q = qty_for_risk(risk_usd, entry, sl, est_cost_frac, with_costs)
    return q * (abs(entry - sl) + cost_per_unit(entry, est_cost_frac))


def overrun(entry: float, sl: float, est_cost_frac: float) -> float:
    """Cuánto se pasa hoy del riesgo declarado, como fracción (0,167 = 16,7 % de más)."""
    return cost_r(entry, sl, est_cost_frac)
