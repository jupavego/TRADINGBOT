"""Reglas nativas del agente `regime` (etiquetas de tramo, cambio de régimen bayesiano). Puras."""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, steady

REGIME, UNSTABLE = "metrics.regime", "metrics.unstable"
EXPOSES = frozenset({REGIME, UNSTABLE})
_SIDE = {"trend_up": 1, "trend_down": -1}


def regimen_tramo(v: View, p: dict) -> Signal:
    """Largo en `trend_up`, corto en `trend_down`; sale cuando cambia la etiqueta."""
    lab = v.get(REGIME)
    return steady(_SIDE.get(lab, 0)) if lab is not None else NONE


def regimen_tramo_estable(v: View, p: dict) -> Signal:
    """Como `regimen_tramo`, y solo entra si `unstable` es falso."""
    lab = v.get(REGIME)
    if lab is None:
        return NONE
    side = _SIDE.get(lab, 0)
    return Signal(enter=side if v.get(UNSTABLE) is False else 0, hold=side)


RULES = {"regimen_tramo": regimen_tramo, "regimen_tramo_estable": regimen_tramo_estable}
