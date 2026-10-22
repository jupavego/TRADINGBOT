"""Contabilidad de la cuenta simulada: liquidación por posición, suelo del capital y drawdown.

Margen AISLADO, como en los futuros del exchange: una posición no puede perder más que su margen.
Si el precio de salida que devolvió el motor quedó al otro lado del precio de liquidación (un hueco
que atravesó el stop) la cuenta real ya habría liquidado la posición: se cierra como `LIQ` con la
pérdida del margen completo, no con la pérdida imposible del hueco. Con ese tope por posición el
capital de la cuenta no puede quedar negativo (cada cierre resta como mucho el margen que ya
estaba apartado) y el drawdown no puede pasar del 100 %.

Sin recargas de capital: cuando el capital REALIZADO baja del suelo (`min_equity_frac` del
inicial) el perfil queda AGOTADO, deja de abrir y mantiene lo abierto hasta su cierre. Una cuenta
agotada no vuelve: si algún día se quieren recargas serán un movimiento explícito y contabilizado
aparte. Todo es SIMULADO.
"""

from __future__ import annotations

import math

import numpy as np

from eim.paper.params import ProfileParams

LIQ = "LIQUIDACION"           # motivo de cierre propio: no es una salida de la estrategia


def leverage_for(p: ProfileParams, entry: float, sl: float, mmr: float) -> int:
    """Apalancamiento entero tal que la liquidación quede a ≥ `liq_buffer` × la distancia al SL."""
    dist = abs(entry - sl) / entry
    return max(1, min(p.max_leverage, math.floor(1 / (p.liq_buffer * dist + mmr))))


def liq_price(side: int, entry: float, lev: int, mmr: float) -> float:
    return entry * (1 - side * (1 / lev - mmr))


def capped(pnl: float, margin: float, side: int, price: float | None,
           liq: float | None) -> tuple[float, str]:
    """(PnL que la cuenta puede perder de esa posición, motivo de la liquidación o «»).

    `price` es la salida de un cierre o la marca de una posición abierta. Hay liquidación si ese
    precio quedó al otro lado del precio de liquidación o si la pérdida calculada supera el margen
    (lo segundo no debería ocurrir con el primero cubierto: si ocurre, el motivo lo dice)."""
    gap = price is not None and liq is not None and (price - liq) * side <= 0
    if not gap and pnl >= -margin:
        return pnl, ""
    why = (f"el precio {price:g} atravesó la liquidación {liq:g}" if gap
           else f"la pérdida calculada {pnl:+.2f} USDT supera el margen {margin:.2f} USDT")
    return -margin, why


def exhausted(p: ProfileParams, equity: float) -> str | None:
    """Motivo si el capital realizado ya no permite operar (cuenta agotada); None si sigue viva.

    El suelo es una fracción del capital inicial: por debajo de ella el riesgo por operación queda
    tan pequeño que ninguna posición negociable cabe, y seguir «operando» sería inventar cuenta."""
    floor = p.initial_equity * p.min_equity_frac
    if equity > floor:
        return None
    return (f"cuenta agotada: capital realizado {equity:.2f} USDT ≤ {floor:.2f} USDT "
            f"({p.min_equity_frac:.0%} del inicial); no se abren posiciones nuevas")


def max_dd_pct(curve: list[tuple[int, float]]) -> float:
    """Máximo descenso sobre la curva de `equity` (0..1), medido desde el máximo previo.

    Con el suelo de la cuenta la curva nunca baja de 0, así que esto no puede pasar de 1: si pasa,
    es un error de contabilidad (lo prohíbe `tests/paper/test_account.py`)."""
    if not curve:
        return 0.0
    eq = np.array([x for _, x in curve])
    peak = np.maximum.accumulate(eq)
    return float(((peak - eq) / np.where(peak > 0, peak, 1.0)).max())
