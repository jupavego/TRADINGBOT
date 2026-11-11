"""Reglas nativas del agente `elliott` (zigzag etiquetado 0…C). Puras.

Aviso para el examen físico (T169): el agente etiqueta siempre los **últimos** pivotes y el último
queda en «C», así que «el último pivote confirmado es el 2 (o el 5)» casi nunca se cumple. La regla
se escribe tal como la aprobó el usuario; si no opera, la baja por cadencia es el veredicto.
"""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View

M = "metrics."
LABEL, KIND, VALID, PUP = M + "pivots[-1].wave_label", M + "pivots[-1].type", \
    M + "valid_count", M + "prob_up_pct"
EXPOSES = frozenset({LABEL, KIND, VALID, PUP})


def _after(v: View, label: str) -> int:
    """Lado de la onda siguiente cuando el último pivote pasa a `label` con conteo válido: tras un
    mínimo (L), largo; tras un máximo (H), corto."""
    if v.get(LABEL) != label or v.get(LABEL, 1) == label or v.get(VALID) is not True:
        return 0
    return {"L": 1, "H": -1}.get(v.get(KIND), 0)


def elliott_onda3(v: View, p: dict) -> Signal:
    """Se confirma el pivote 2: entra en la dirección de la onda 1; sale al confirmarse el 3."""
    if v.get(LABEL) is None:
        return NONE
    return Signal(enter=_after(v, "2"), hold=0 if v.get(LABEL) == "3" else None)


def elliott_onda5_giro(v: View, p: dict) -> Signal:
    """Se confirma el pivote 5: entra contra el impulso; sale al confirmarse el pivote A."""
    if v.get(LABEL) is None:
        return NONE
    return Signal(enter=_after(v, "5"), hold=0 if v.get(LABEL) == "A" else None)


RULES = {"elliott_onda3": elliott_onda3, "elliott_onda5_giro": elliott_onda5_giro}
