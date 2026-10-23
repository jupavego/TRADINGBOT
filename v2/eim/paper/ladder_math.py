"""Fórmulas de la protección progresiva (PPP): neto estimado, precio de protección y escalones.

Funciones puras (sin estado). Beneficio neto estimado de salir a un precio `p` (misma contabilidad
que `engine.Outcome.net`, en USDT con `qty` del activo y entrada `f`):
    neto(p) = qty·(lado·(p − f) − fee_sal·p) − qty·f·(fee_ent + desl_ent + desl_sal + funding)
Precio de protección del nivel L (despeje exacto; luego se redondea al tick EN CONTRA del
operador —largo arriba, corto abajo— y se vuelve a comprobar `neto ≥ L`):
    largo : p = (L/qty + f·(1+K)) / (1 − fee_sal)       K = fee_ent+desl_ent+desl_sal+funding
    corto : p = (f·(1−K) − L/qty) / (1 + fee_sal)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from eim.paper.params import ExecParams

EPS = 1e-9


@dataclass(frozen=True)
class LadderCosts:
    """Costos de entrada (ya conocidos) y de salida a SL (estimados), como fracciones."""

    fee_in: float
    slip_in: float
    fee_out: float
    slip_out: float


def net_usd(side: int, qty: float, fill: float, price: float, funding: float,
            c: LadderCosts) -> float:
    """Beneficio neto (USDT) de cerrar `qty` a `price`, con todos los costos modelados."""
    k = c.fee_in + c.slip_in + c.slip_out + funding
    return qty * (side * (price - fill) - c.fee_out * price) - qty * fill * k


def protect_price(side: int, qty: float, fill: float, level: float, funding: float,
                  c: LadderCosts, tick: float) -> float:
    """Precio de SL cuyo neto estimado es `level` USDT, redondeado al tick y verificado."""
    k = c.fee_in + c.slip_in + c.slip_out + funding
    if side > 0:
        exact = (level / qty + fill * (1 + k)) / (1 - c.fee_out)
        n = math.ceil(exact / tick - EPS)
    else:
        exact = (fill * (1 - k) - level / qty) / (1 + c.fee_out)
        n = math.floor(exact / tick + EPS)
    for _ in range(5):                       # el redondeo nunca puede dejar el neto bajo el nivel
        price = round(n * tick, 8)
        if net_usd(side, qty, fill, price, funding, c) >= level - EPS:
            return price
        n += side
    return round(n * tick, 8)


def level_of(max_float: float, first: float, step: float) -> int:
    """Escalón confirmado por el beneficio neto máximo (0 = aún sin protección)."""
    if max_float + EPS < first:
        return 0
    return 1 + int(math.floor((max_float - first) / step + EPS))


def nominal(level: int, first: float, step: float) -> float:
    """Beneficio neto nominal protegido por un escalón (10, 15, 20, …)."""
    return first + (level - 1) * step if level > 0 else 0.0


def floor_qty(qty: float, qty_step: float) -> float:
    return math.floor(qty / qty_step + EPS) * qty_step


def costs_for(fee_in: float, slip_in: float, ep: ExecParams) -> LadderCosts:
    cp = ep.costs
    return LadderCosts(fee_in, slip_in, cp.taker_fee, cp.slip_base_bps / 1e4)
