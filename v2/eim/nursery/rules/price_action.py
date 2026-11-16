"""Reglas nativas del agente `price_action` (BOS/CHOCH, patrones y zonas). Puras."""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, num

M = "metrics."
EVENT, AGE, STATE = M + "last_event", M + "last_event_age", M + "structure_state"
BULL, BEAR, ZONES = M + "bullish_patterns", M + "bearish_patterns", M + "sr_zones"
EXPOSES = frozenset({EVENT, AGE, STATE, BULL, BEAR, ZONES})
_BOS = {"BOS_ALCISTA": 1, "BOS_BAJISTA": -1}
_CHOCH = {"CHOCH_ALCISTA": 1, "CHOCH_BAJISTA": -1}


def _new(v: View, table: dict[str, int]) -> int:
    age = num(v.get(AGE))
    return table.get(v.get(EVENT), 0) if age == 0 else 0


def _choch_hold(v: View) -> int | None:
    """Un CHOCH (nuevo o vigente) manda hacia su lado; si no lo hay, la regla no opina."""
    return _CHOCH.get(v.get(EVENT)) or None


def pa_bos(v: View, p: dict) -> Signal:
    """BOS nuevo (edad 0): entra a favor; sale con un CHOCH contrario."""
    return Signal(enter=_new(v, _BOS), hold=_choch_hold(v))


def pa_choch(v: View, p: dict) -> Signal:
    """CHOCH nuevo (edad 0): entra en su dirección; sale con un CHOCH contrario."""
    return Signal(enter=_new(v, _CHOCH), hold=_choch_hold(v))


def _near_zone(v: View, side: int, tol_pct: float) -> bool:
    """¿Hay una zona S/R a ≤ tol_pct % del cierre, por debajo (soporte) o encima (resistencia)?"""
    c, zones = v.close, v.get(ZONES)
    if c is None or not isinstance(zones, list):
        return False
    for z in zones:
        px = num(z.get("price")) if isinstance(z, dict) else None
        if px is not None and (c - px) * side >= 0 and abs(c - px) / c * 100 <= tol_pct:
            return True
    return False


def pa_patron_zona(v: View, p: dict) -> Signal:
    """≥ 1 patrón alcista (bajista) en la ventana del agente cerca de un soporte (resistencia)."""
    bull, bear = num(v.get(BULL)) or 0, num(v.get(BEAR)) or 0
    tol = float(p["sr_tolerance_pct"])
    sides = [s for s, n in ((1, bull), (-1, bear)) if n >= 1 and _near_zone(v, s, tol)]
    return Signal(enter=sides[0]) if len(sides) == 1 else NONE


def pa_bos_patron(v: View, p: dict) -> Signal:
    """BOS nuevo solo si hay ≥ 1 patrón del mismo signo en la ventana del agente."""
    side = _new(v, _BOS)
    n = (num(v.get(BULL if side > 0 else BEAR)) or 0) if side else 0
    return Signal(enter=side if side and n >= 1 else 0, hold=_choch_hold(v))


RULES = {"pa_bos": pa_bos, "pa_choch": pa_choch, "pa_patron_zona": pa_patron_zona,
         "pa_bos_patron": pa_bos_patron}
