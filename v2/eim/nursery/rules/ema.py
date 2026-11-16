"""Reglas nativas del agente `ema` (FRM: pila de medias 9/21/55/100/200). Puras."""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, num, steady

V = "metrics.variables."
EXPOSES = frozenset(V + k for k in (
    "STACK_ORDER", "PRICE_VS_STACK", "EMA_21", "EMA_200", "SLOPE_DIRECTION",
    "COMPRESSION_INDEX", "COMPRESSION_DURATION", "ELASTICITY", "BOUNCE_COUNT_21"))
_STACK = {"BULL_PERFECT": 1, "BEAR_PERFECT": -1}
_SLOPE = {"UP": 1, "DOWN": -1}


def ema_pila(v: View, p: dict) -> Signal:
    """Pila perfecta con el cierre del lado bueno de la EMA 200 (PRICE_VS_STACK cuenta cuántas
    medias quedan por debajo del cierre: ≥ 1 en largo, ≤ 4 en corto)."""
    side = _STACK.get(v.get(V + "STACK_ORDER"), 0)
    above = num(v.get(V + "PRICE_VS_STACK"))
    if above is None:
        return NONE
    ok = (side > 0 and above >= 1) or (side < 0 and above <= 4)
    return steady(side if ok else 0)


def ema_resorte(v: View, p: dict) -> Signal:
    """La compresión (≤ θ-001 durante ≥ θ-006 velas) se rompe: entra según la pendiente."""
    ci, ci0 = num(v.get(V + "COMPRESSION_INDEX")), num(v.get(V + "COMPRESSION_INDEX", 1))
    dur0 = num(v.get(V + "COMPRESSION_DURATION", 1))
    if ci is None or ci0 is None or dur0 is None:
        return NONE
    th = float(p["theta_001_compress"])
    if not (ci0 <= th < ci and dur0 >= float(p["theta_006_duration"])):
        return NONE
    return Signal(enter=_SLOPE.get(v.get(V + "SLOPE_DIRECTION"), 0))


def ema_retroceso(v: View, p: dict) -> Signal:
    """Con la pila en orden, un toque nuevo de la EMA 21 (sube BOUNCE_COUNT_21) y cierre a favor."""
    side = _STACK.get(v.get(V + "STACK_ORDER"), 0)
    b, b0, e21 = (num(v.get(V + "BOUNCE_COUNT_21")), num(v.get(V + "BOUNCE_COUNT_21", 1)),
                  num(v.get(V + "EMA_21")))
    if not side or b is None or b0 is None or e21 is None or v.close is None:
        return NONE
    return Signal(enter=side if b > b0 and (v.close - e21) * side > 0 else 0)


def ema_elastico(v: View, p: dict) -> Signal:
    """Precio estirado ≥ θ-003 % sobre la EMA 200: entra en contra, objetivo la EMA 21."""
    el, e21 = num(v.get(V + "ELASTICITY")), num(v.get(V + "EMA_21"))
    if el is None or e21 is None:
        return NONE
    th = float(p["theta_003_elastic"])
    side = -1 if el >= th else 1 if el <= -th else 0
    return Signal(enter=side, target=e21) if side else NONE


RULES = {"ema_pila": ema_pila, "ema_resorte": ema_resorte, "ema_retroceso": ema_retroceso,
         "ema_elastico": ema_elastico}
