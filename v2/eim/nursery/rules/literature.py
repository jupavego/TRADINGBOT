"""Reglas nativas del agente `literature` (aciertos de las fichas de la biblioteca). Puras."""

from __future__ import annotations

from eim.nursery.rules.base import NONE, Signal, View, num, sign

M = "metrics."
CARD, DIR, STRENGTH = M + "hits[].card_id", M + "hits[].direction", M + "hits[].strength"
EXPOSES = frozenset({CARD, DIR, STRENGTH})


def _hits(v: View, with_strength: bool = True) -> list[tuple[str, int, float]]:
    """(ficha, dirección, fuerza) de los aciertos de la vela; listas paralelas del reporte."""
    cards, dirs = v.get(CARD) or [], v.get(DIR) or []
    strs = (v.get(STRENGTH) or []) if with_strength else [1.0] * len(cards)
    if not (len(cards) == len(dirs) == len(strs)):
        return []
    return [(str(c), sign(num(d)), num(s) or 0.0)
            for c, d, s in zip(cards, dirs, strs, strict=True)]


def lit_consenso(v: View, p: dict) -> Signal:
    """Signo de Σ dirección·fuerza de los aciertos, con al menos min_hits aciertos."""
    dirs, strs = v.get(DIR) or [], v.get(STRENGTH) or []
    if len(dirs) != len(strs) or len(dirs) < int(p["min_hits"]):
        return NONE
    return Signal(enter=sign(sum(sign(num(d)) * (num(s) or 0.0)
                                 for d, s in zip(dirs, strs, strict=True))))


def _card(v: View, card: str) -> int:
    hits = [d for c, d, _ in _hits(v, with_strength=False) if c == card and d]
    return hits[0] if len(set(hits)) == 1 else 0


def lit_regla_4_semanas(v: View, p: dict) -> Signal:
    """Acierto `murphy_weekly_rule` (Donchian de `weeks` semanas): entra; sale con el contrario."""
    side = _card(v, "murphy_weekly_rule")
    return Signal(enter=side, hold=side or None)


def lit_nison_giro(v: View, p: dict) -> Signal:
    """El acierto más fuerte entre las fichas `nison_*` (exigen tendencia previa ≥ trend_atr)."""
    nison = [(s, d) for c, d, s in _hits(v) if c.startswith("nison_") and d]
    if not nison:
        return NONE
    best = max(s for s, _ in nison)
    sides = {d for s, d in nison if s == best}
    return Signal(enter=sides.pop()) if len(sides) == 1 else NONE


def lit_murphy_rsi(v: View, p: dict) -> Signal:
    """Acierto `murphy_rsi` (RSI 14 que vuelve a cruzar 30 o 70)."""
    return Signal(enter=_card(v, "murphy_rsi"))


RULES = {"lit_consenso": lit_consenso, "lit_regla_4_semanas": lit_regla_4_semanas,
         "lit_nison_giro": lit_nison_giro, "lit_murphy_rsi": lit_murphy_rsi}
