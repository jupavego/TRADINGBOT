"""Reglas nativas del agente `structure` (escenarios BRM SC-01…SC-05). Puras."""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, num, sign

M = "metrics."
SCEN, CONV, STATE, BIAS = M + "scenario", M + "conviction", M + "structural_state", "bias"
EXPOSES = frozenset({SCEN, CONV, STATE, BIAS})


def _is(scen: object, code: str) -> bool:
    return isinstance(scen, str) and scen.startswith(code)


def _enters(v: View, p: dict, code: str) -> int:
    """Sentido del sesgo cuando el escenario PASA a `code` con convicción ≥ conviction_min."""
    conv = num(v.get(CONV))
    if conv is None or conv < float(p["conviction_min"]):
        return 0
    if not _is(v.get(SCEN), code) or _is(v.get(SCEN, 1), code) or not v.has(1):
        return 0
    return sign(num(v.get(BIAS)))


def estructura_continuacion(v: View, p: dict) -> Signal:
    """Pasa a SC-01 (continuación): entra con el sesgo; sale cuando cambia el escenario."""
    scen = v.get(SCEN)
    if scen is None:
        return NONE
    hold = sign(num(v.get(BIAS))) if _is(scen, "SC-01") else 0
    return Signal(enter=_enters(v, p, "SC-01"), hold=hold)


def estructura_ruptura(v: View, p: dict) -> Signal:
    return Signal(enter=_enters(v, p, "SC-02"))


def estructura_cambio(v: View, p: dict) -> Signal:
    return Signal(enter=_enters(v, p, "SC-04"))


def estructura_retroceso(v: View, p: dict) -> Signal:
    return Signal(enter=_enters(v, p, "SC-03"))


RULES = {"estructura_continuacion": estructura_continuacion,
         "estructura_ruptura": estructura_ruptura, "estructura_cambio": estructura_cambio,
         "estructura_retroceso": estructura_retroceso}
