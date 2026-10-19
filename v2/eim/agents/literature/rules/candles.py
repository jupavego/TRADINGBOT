"""Reglas de velas de Nison (T52): una función pura por ficha, evaluada en la vela cerrada `i`."""

from __future__ import annotations

import math

from eim.agents.literature.params import LiteratureParams
from eim.agents.literature.rules.base import Condition as C
from eim.agents.literature.rules.base import Ctx, RuleHit, clip01


def _hit(x: Ctx, i: int, card: str, d: int, s: float, p: LiteratureParams, label: str,
         conds: list[C]) -> RuleHit:
    return RuleHit(card_id=card, direction=d, strength=clip01(s), horizon_bars=p.horizon_bars,
                   t=int(x.t[i]), price=float(x.c[i]), timeframe=x.timeframe, label=label,
                   conditions=tuple(conds))


def _single(x: Ctx, i: int, p: LiteratureParams, d: int) -> tuple[float, float, list[C]] | None:
    """Forma de martillo (d=+1, sombra inferior larga) o estrella fugaz (d=−1, superior)."""
    rng = x.rng(i)
    if not rng > 0:
        return None
    body = max(x.body(i), 1e-9 * x.c[i])
    long_s = (x.bot(i) - x.lo[i]) if d > 0 else (x.h[i] - x.top(i))
    short_s = (x.h[i] - x.top(i)) if d > 0 else (x.bot(i) - x.lo[i])
    edge = (x.top(i) - x.lo[i]) / rng if d > 0 else (x.h[i] - x.bot(i)) / rng
    ratio = long_s / body
    tr = x.trend(i - 1, p)
    shape = ratio >= p.shadow_ratio and short_s <= p.far_shadow_frac * rng \
        and edge >= 1 - p.body_edge_frac
    if not shape or math.isnan(tr) or (-d) * tr < p.trend_atr:
        return None
    conds = [C("sombra larga / cuerpo", round(ratio, 2)),
             C("sombra opuesta / rango", round(short_s / rng, 2)),
             C("tendencia previa (ATR)", round(tr, 2))]
    strength = 0.5 + 0.5 * clip01((ratio - p.shadow_ratio) / (p.shadow_ratio_full - p.shadow_ratio))
    return strength, ratio, conds


def hammer(x: Ctx, p: LiteratureParams, i: int) -> RuleHit | None:
    r = _single(x, i, p, +1)
    return None if r is None else _hit(x, i, "nison_hammer", +1, r[0], p,
                                       "Martillo tras descenso", r[2])


def shooting_star(x: Ctx, p: LiteratureParams, i: int) -> RuleHit | None:
    r = _single(x, i, p, -1)
    return None if r is None else _hit(x, i, "nison_shooting_star", -1, r[0], p,
                                       "Estrella fugaz tras subida", r[2])


def engulfing(x: Ctx, p: LiteratureParams, i: int) -> RuleHit | None:
    j = i - 1
    prev_doji = x.rng(j) > 0 and x.body(j) <= p.doji_frac * x.rng(j)
    if x.body(i) <= 0 or x.top(i) < x.top(j) or x.bot(i) > x.bot(j) \
            or (x.top(i) == x.top(j) and x.bot(i) == x.bot(j)):
        return None
    d = +1 if x.white(i) and (x.black(j) or prev_doji) else -1 if x.black(i) and (
        x.white(j) or prev_doji) else 0
    if d == 0:
        return None
    tr = x.trend(j, p)
    if math.isnan(tr) or (-d) * tr < p.trend_atr:
        return None
    small_first = x.body(j) < 0.5 * x.body(i)
    extended = abs(tr) >= p.mature_trend_atr
    vol = x.vol_high(i, p)
    s = 0.5 + 0.2 * small_first + 0.15 * extended + 0.15 * vol
    conds = [C("cuerpo 2.ª envuelve a la 1.ª", "sí"), C("tendencia previa (ATR)", round(tr, 2)),
             C("1.ª pequeña frente a 2.ª", "sí" if small_first else "no", small_first),
             C("movimiento previo extenso", "sí" if extended else "no", extended),
             C("volumen alto en la 2.ª", "sí" if vol else "no", vol)]
    return _hit(x, i, "nison_engulfing", d, s, p,
                "Envolvente alcista" if d > 0 else "Envolvente bajista", conds)


def _star(x: Ctx, p: LiteratureParams, i: int, d: int) -> RuleHit | None:
    a, b = i - 2, i - 1
    first_ok = (x.black(a) if d > 0 else x.white(a)) and x.body(a) >= p.long_body_atr * x.atr[i]
    if not first_ok:
        return None
    star_small = x.body(b) <= p.small_body_frac * x.body(a)
    tol = p.star_gap_atr * x.atr[i]
    sep = (x.top(b) <= x.bot(a) + tol) if d > 0 else (x.bot(b) >= x.top(a) - tol)
    third = x.white(i) if d > 0 else x.black(i)
    mid = x.bot(a) + p.penetration * x.body(a) if d > 0 else x.top(a) - p.penetration * x.body(a)
    pen_ok = x.c[i] > mid if d > 0 else x.c[i] < mid
    tr = x.trend(a, p)
    if not (star_small and sep and third and pen_ok) or math.isnan(tr) or (-d) * tr < p.trend_atr:
        return None
    depth = abs(x.c[i] - (x.c[a] if d > 0 else x.o[a])) / x.body(a)
    overlap_free = (x.top(b) <= x.bot(a)) if d > 0 else (x.bot(b) >= x.top(a))
    s = 0.5 + 0.25 * clip01(depth - p.penetration) * 2 + 0.25 * overlap_free
    conds = [C("1.ª larga (cuerpo/ATR)", round(x.body(a) / x.atr[i], 2)),
             C("2.ª pequeña (cuerpo 2.ª/1.ª)", round(x.body(b) / x.body(a), 2)),
             C("3.ª cierra dentro de la 1.ª (fracción)", round(depth, 2)),
             C("tendencia previa (ATR)", round(tr, 2))]
    card = "nison_morning_star" if d > 0 else "nison_evening_star"
    return _hit(x, i, card, d, s, p,
                "Estrella de la mañana" if d > 0 else "Estrella vespertina", conds)


def morning_star(x: Ctx, p: LiteratureParams, i: int) -> RuleHit | None:
    return _star(x, p, i, +1)


def evening_star(x: Ctx, p: LiteratureParams, i: int) -> RuleHit | None:
    return _star(x, p, i, -1)


def _three(x: Ctx, p: LiteratureParams, i: int, d: int) -> RuleHit | None:
    ks = (i - 2, i - 1, i)
    col = x.white if d > 0 else x.black
    if not all(col(k) and x.body(k) >= p.long_body_atr * x.atr[i] * 0.75 for k in ks):
        return None
    if not all(d * (x.c[b] - x.c[a]) > 0 for a, b in zip(ks, ks[1:], strict=False)):
        return None
    near = all(((x.h[k] - x.c[k]) if d > 0 else (x.c[k] - x.lo[k])) <= p.close_near_extreme
              * x.rng(k) for k in ks)
    inside = all(x.bot(a) <= x.o[b] <= x.top(a) for a, b in zip(ks, ks[1:], strict=False))
    if not (near and inside):
        return None
    bodies = [x.body(k) for k in ks]
    weakening = bodies[2] < bodies[1] < bodies[0] if d > 0 else False
    if d > 0 and weakening:        # bloque de avance: Nison pide proteger largos, no comprar
        return None
    tr = x.trend(ks[0] - 1, p)
    if math.isnan(tr):
        return None
    if d > 0 and tr > p.trend_atr:           # debe salir de zona baja o lateral
        return None
    if d < 0 and tr < p.trend_atr:           # precios altos / alza madura
        return None
    s = 0.6 + 0.2 * x.vol_high(i, p) + 0.2 * clip01(abs(tr) / p.mature_trend_atr) * (d < 0)
    card = "nison_three_white_soldiers" if d > 0 else "nison_three_black_crows"
    conds = [C("3 velas largas con cierres sucesivos", "sí"),
             C("cierres cerca del extremo", "sí"), C("aperturas dentro del cuerpo previo", "sí"),
             C("tendencia previa (ATR)", round(tr, 2))]
    return _hit(x, i, card, d, s, p,
                "Tres soldados blancos" if d > 0 else "Tres cuervos negros", conds)


def three_white_soldiers(x: Ctx, p: LiteratureParams, i: int) -> RuleHit | None:
    return _three(x, p, i, +1)


def three_black_crows(x: Ctx, p: LiteratureParams, i: int) -> RuleHit | None:
    return _three(x, p, i, -1)
