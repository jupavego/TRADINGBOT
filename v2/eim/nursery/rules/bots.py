"""Reglas nativas del agente `bots` (consenso de bots públicos). Puras."""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, num, steady

M = "metrics."
STANCE, STATUS, DIS = M + "bots[].stance", M + "bots[].status", M + "disagreement"
EXPOSES = frozenset({STANCE, STATUS, DIS})


def _ok_stances(v: View) -> list[float] | None:
    st, ss = v.get(STANCE), v.get(STATUS)
    if not isinstance(st, list) or not isinstance(ss, list) or len(st) != len(ss):
        return None
    return [s for s, k in ((num(a), b) for a, b in zip(st, ss, strict=True))
            if k == "ok" and s is not None]


def bots_mayoria(v: View, p: dict) -> Signal:
    """Más de la mitad de los bots `ok` con postura +1 (largo) o −1 (corto); sale al perderla."""
    ok = _ok_stances(v)
    if not ok:
        return NONE if ok is None else steady(0)
    half = len(ok) / 2
    longs, shorts = sum(1 for s in ok if s > 0), sum(1 for s in ok if s < 0)
    return steady(1 if longs > half else -1 if shorts > half else 0)


def bots_unanimidad(v: View, p: dict) -> Signal:
    """Todos los bots `ok` (≥ min_bots) con la misma postura no nula y desacuerdo 0."""
    ok = _ok_stances(v)
    if ok is None:
        return NONE
    dis = num(v.get(DIS))
    signs = {1 if s > 0 else -1 if s < 0 else 0 for s in ok}
    same = len(ok) >= int(p["min_bots"]) and len(signs) == 1 and 0 not in signs and dis == 0
    return steady(signs.pop() if same else 0)


RULES = {"bots_mayoria": bots_mayoria, "bots_unanimidad": bots_unanimidad}
