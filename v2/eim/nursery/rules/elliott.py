"""Reglas nativas del agente `elliott` (zigzag etiquetado 0…C). Puras.

Aviso para el examen físico (T169): el agente etiqueta siempre los **últimos** pivotes y el último
queda en «C», así que «el último pivote confirmado es el 2 (o el 5)» casi nunca se cumple. La regla
se escribe tal como la aprobó el usuario; si no opera, la baja por cadencia es el veredicto.
"""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, num

M = "metrics."
LABEL, KIND, VALID, PUP = M + "pivots[-1].wave_label", M + "pivots[-1].type", \
    M + "valid_count", M + "prob_up_pct"
PRICE, PRICE3 = M + "pivots[-1].price", M + "pivots[-3].price"
EXPOSES = frozenset({LABEL, KIND, VALID, PUP, PRICE, PRICE3})
_TURN = {"L": 1, "H": -1}


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


def _new_pivot(v: View) -> int:
    """Lado de la oscilación que se acaba de confirmar: un mínimo nuevo (L) abre la subida, un
    máximo nuevo (H) la bajada; 0 si el último pivote no cambió en esta vela."""
    k, k0 = v.get(KIND), v.get(KIND, 1)
    return _TURN.get(k, 0) if k0 is not None and k != k0 else 0


def elliott_oscilacion(v: View, p: dict) -> Signal:
    """T177. Sigue la oscilación del zigzag del agente (sin etiquetas de onda): entra al
    confirmarse un pivote y sale al confirmarse el siguiente."""
    k = v.get(KIND)
    if k is None:
        return NONE
    return Signal(enter=_new_pivot(v), hold=_TURN.get(k, 0))


def elliott_dow(v: View, p: dict) -> Signal:
    """T177. Teoría de Dow sobre los mismos pivotes: largo solo con un mínimo más alto que el
    anterior, corto solo con un máximo más bajo; sale al confirmarse el pivote siguiente."""
    k = v.get(KIND)
    if k is None:
        return NONE
    side = _new_pivot(v)
    px, px3 = num(v.get(PRICE)), num(v.get(PRICE3))
    dow = side != 0 and px is not None and px3 is not None and (px - px3) * side > 0
    return Signal(enter=side if dow else 0, hold=_TURN.get(k, 0))


def elliott_tendencia_dow(v: View, p: dict) -> Signal:
    """T177. Dow a favor de la tendencia en el retroceso: al confirmarse un máximo más alto que el
    anterior, largo (compra el retroceso de la subida); al confirmarse un mínimo más bajo, corto
    (vende el rebote de la bajada). Sale a las 12 velas del agente (`time_stop`)."""
    k = v.get(KIND)
    if k is None:
        return NONE
    turn = _new_pivot(v)
    px, px3 = num(v.get(PRICE)), num(v.get(PRICE3))
    if not turn or px is None or px3 is None:
        return NONE
    return Signal(enter=-turn if (px - px3) * -turn > 0 else 0)


RULES = {"elliott_onda3": elliott_onda3, "elliott_onda5_giro": elliott_onda5_giro,
         "elliott_oscilacion": elliott_oscilacion, "elliott_dow": elliott_dow,
         # T177: ocupa la plaza de `regimen_tramo` (el agente `regime` no llega a la cadencia).
         "elliott_tendencia_dow": elliott_tendencia_dow}
