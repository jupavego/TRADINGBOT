"""Análisis de un marco (votos → familias → sesgo) y construcción de los marcos vecinos."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from eim.agents.technical.combine import (
    FamilyPlan,
    bias_series,
    family_votes,
    plan_families,
    regime_series,
)
from eim.agents.technical.params import TechnicalParams
from eim.agents.technical.rules import Ctx, Rule, evaluate
from eim.core import Candle
from eim.indicators import candle_arrays


@dataclass(frozen=True)
class FrameResult:
    votes: dict[str, np.ndarray]
    info: dict[str, str]
    plan: FamilyPlan
    families: dict[str, np.ndarray]
    regime: np.ndarray
    adx: np.ndarray
    width_pct: np.ndarray
    bias: np.ndarray
    ctx: Ctx


def analyze_arrays(data: dict[str, np.ndarray], p: TechnicalParams,
                   rules: dict[str, Rule], plan: FamilyPlan | None = None) -> FrameResult:
    """Analiza un marco. `plan` fijo (p. ej. estimado en otra muestra) o calculado aquí."""
    ctx = Ctx(data=data, rp=p.rules)
    votes, info = evaluate(ctx, rules)
    family_of = {k: r.family for k, r in rules.items()}
    plan = plan or plan_families(votes, family_of, p)
    fam = family_votes(votes, plan, p)
    regime, adx, pct = regime_series(ctx, p)
    return FrameResult(votes, info, plan, fam, regime, adx, pct, bias_series(fam, regime, p), ctx)


def analyze(candles: Sequence[Candle], p: TechnicalParams, rules: dict[str, Rule]) -> FrameResult:
    return analyze_arrays(candle_arrays(candles), p, rules)


def resample(candles: Sequence[Candle], step_ms: int) -> list[Candle]:
    """Agrega velas a un marco superior; solo grupos completos (se descarta el incompleto)."""
    if not candles:
        return []
    gaps = (b.t - a.t for a, b in zip(candles, candles[1:], strict=False))
    base = min(gaps, default=step_ms)
    need = max(1, step_ms // base) if base > 0 else 1
    groups: dict[int, list[Candle]] = {}
    for c in candles:
        groups.setdefault(c.t // step_ms * step_ms, []).append(c)
    out: list[Candle] = []
    for t, g in groups.items():
        if len(g) != need:
            continue
        buy = [c.taker_buy_v for c in g]
        trades = [c.trades for c in g]
        out.append(Candle(
            t=t, o=g[0].o, h=max(c.h for c in g), l=min(c.l for c in g), c=g[-1].c,
            v=sum(c.v for c in g),
            taker_buy_v=None if any(b is None for b in buy) else sum(buy),  # type: ignore[arg-type]
            trades=None if any(x is None for x in trades) else sum(trades),  # type: ignore[arg-type]
        ))
    return out


def neighbors(timeframe: str, p: TechnicalParams) -> tuple[str | None, str | None]:
    """Marco inferior y superior en la escalera de `tf_minutes`."""
    ladder = sorted(p.tf_minutes, key=p.tf_minutes.__getitem__)
    if timeframe not in ladder:
        return None, None
    i = ladder.index(timeframe)
    lower = ladder[i - 1] if i > 0 else None
    upper = ladder[i + 1] if i + 1 < len(ladder) else None
    return lower, upper
