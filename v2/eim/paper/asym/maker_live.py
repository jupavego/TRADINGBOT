"""T189 — entrada límite por defecto, medida en vivo y por marco (también 15 m).

Es la medición de T143 (`eim/paper/maker_ab.py`) llevada a las ideas decididas en tiempo real:
cada idea viva a mercado se simula como salió (taker) y como orden límite al precio pedido con
`MAKER_BARS` velas de vigencia (maker). La no ejecución cuenta como 0 R y el R va sobre el riesgo
**planeado** (`net_p`), el mismo en los dos brazos (T143, decisión 1). T143 adoptó maker en 1 h y
4 h con el banco de T131, que no tiene 15 m: aquí 15 m se mide por primera vez.

Puro: recibe ideas ya construidas y el camino de precios.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from eim.paper.asym import prereg as P
from eim.paper.engine import Outcome, Path
from eim.paper.ideas import Idea
from eim.paper.maker_ab import Leg, arm_stats, pair_up
from eim.paper.params import ExecParams

CONTROL = "control_aleatorio"


@dataclass(frozen=True)
class MakerPair:
    idea_id: str
    timeframe: str
    day: int
    t: int
    taker: Leg
    maker: Leg

    @property
    def delta(self) -> float:
        return self.maker.net_p - self.taker.net_p


def live_market_ideas(outcomes: Iterable[Outcome], skip: set[str] = frozenset()) -> list[Idea]:
    """Ideas vivas a mercado desde el inicio del pre-registro, sin el control ni las ya medidas."""
    out = []
    for o in outcomes:
        i = o.idea
        if (i.origin == "vivo" and i.kind == "market" and i.t >= P.START_MS
                and i.timeframe in P.MAKER_TIMEFRAMES and i.family != "control"
                and i.strategy != CONTROL and i.id not in skip):
            out.append(i)
    return sorted(out, key=lambda x: (x.t, x.id))


def pair_ideas(ideas: Sequence[Idea], path: Path, ep: ExecParams) -> list[MakerPair]:
    """Las dos versiones de cada idea; las que aún no se resuelven en algún brazo no salen."""
    tk, mk, kept, _ = pair_up(ideas, path, ep, P.MAKER_BARS)
    return [MakerPair(ideas[k].id, ideas[k].timeframe, ideas[k].t // P.DAY_MS, ideas[k].t, a, b)
            for k, a, b in zip(kept, tk, mk, strict=True)]


def summary(pairs: Sequence[MakerPair]) -> dict:
    """Los dos brazos con las lecturas de T143 y la caída del costo, para un marco."""
    taker = arm_stats([p.taker for p in pairs])
    maker = arm_stats([p.maker for p in pairs])
    drop = (taker["costo_r"] - maker["costo_r"]) if pairs else 0.0
    return {"n": len(pairs), "taker": taker, "maker": maker, "costo_baja_r": drop}


def halves_same_sign(pairs: Sequence[MakerPair]) -> bool:
    """El signo de ΔE[R] es el mismo en la primera y la segunda mitad (por tiempo)."""
    s = sorted(pairs, key=lambda p: (p.t, p.idea_id))
    if len(s) < 2:
        return False
    k = len(s) // 2
    a = sum(p.delta for p in s[:k]) / k
    b = sum(p.delta for p in s[k:]) / (len(s) - k)
    return (a > 0 and b > 0) or (a < 0 and b < 0)
