"""Reglas nativas del agente `liquidations` (flujo de liquidaciones multibolsa). Puras.

Los umbrales `z_active`, `z_calm` y `min_flow_usd` son los del propio agente: ya deciden su
`state`, así que la regla solo lee la transición del estado.
"""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, num, sign

M = "metrics."
STATE, IMB, BIAS, VENUES = M + "state", M + "imbalance", "bias", M + "venues"
EXPOSES = frozenset({STATE, IMB, BIAS, VENUES})


def _turns(v: View, state: str) -> bool:
    return v.get(STATE) == state and v.has(1) and v.get(STATE, 1) != state


def liq_agotamiento(v: View, p: dict) -> Signal:
    """El estado pasa a `exhausted`: entra en el signo del sesgo (contrario a la cascada)."""
    return Signal(enter=sign(num(v.get(BIAS)))) if _turns(v, "exhausted") else NONE


def liq_cascada(v: View, p: dict) -> Signal:
    """El estado pasa a `active`: entra en el signo del desequilibrio."""
    return Signal(enter=sign(num(v.get(IMB)))) if _turns(v, "active") else NONE


def liq_cascada_multibolsa(v: View, p: dict) -> Signal:
    """Como `liq_cascada`, solo con flujo en ≥ min_venues bolsas."""
    ven = v.get(VENUES)
    if not isinstance(ven, list) or len(ven) < int(p["min_venues"]):
        return NONE
    return liq_cascada(v, p)


RULES = {"liq_agotamiento": liq_agotamiento, "liq_cascada": liq_cascada,
         "liq_cascada_multibolsa": liq_cascada_multibolsa}
