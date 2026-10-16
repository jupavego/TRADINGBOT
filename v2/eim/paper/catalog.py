"""Catálogo de estrategias y generación de ideas a partir de los contextos guardados."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from eim.core import Candle
from eim.paper.ideas import HOUR_MS, Idea, StrategyInfo, to_idea
from eim.paper.strategies import CORE
from eim.paper.strategies_ind import IND, Ind

CATALOG: dict[str, StrategyInfo] = {s.id: s for s in CORE + IND}


def generate_ideas(ctxs: Sequence[dict], candles: Sequence[Candle], symbol: str, bar_ms: int,
                   origin_of: Callable[[dict], str] | None = None,
                   catalog: dict[str, StrategyInfo] | None = None,
                   timeframe: str = "1h", htf: Callable[[int], int] | None = None
                   ) -> list[Idea]:
    """Todas las ideas candidatas, en orden de tiempo y de catálogo.

    `candles` = serie de decisión (1 h) que cubre los contextos; cada estrategia ve el índice de
    la última vela cerrada en `ctx["t"]` (abrió en `t − bar_ms`), nunca una posterior.
    """
    cat = catalog or CATALOG
    ind = Ind(candles)
    out: list[Idea] = []
    for raw in sorted(ctxs, key=lambda c: c["t"]):
        ctx = {**raw, "symbol": symbol, "bar_h": bar_ms / HOUR_MS, "tf": timeframe,
               "htf_dir": htf(int(raw["t"])) if htf else 0}
        i = ind.index(int(ctx["t"]) - bar_ms)
        origin = origin_of(raw) if origin_of else raw.get("origin", "backtest")
        for info in cat.values():
            needs_ind = info.family == "indicadores"
            if needs_ind and i < 0:
                continue
            try:
                d = info.fn(ctx, ind, i)
            except (KeyError, TypeError, ValueError, IndexError):
                d = None   # contexto incompleto (versión vieja o agente sin datos)
            if d is None:
                continue
            idea = to_idea(info, d, ctx, symbol, origin)
            if idea is not None:
                out.append(idea)
    return out
