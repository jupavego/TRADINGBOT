"""Reglas de Murphy (T52): RSI de Wilder (recruce de 30/70) y ruptura de canal de 4 semanas."""

from __future__ import annotations

import math

from eim.agents.literature.params import LiteratureParams
from eim.agents.literature.rules.base import Condition as C
from eim.agents.literature.rules.base import Ctx, RuleHit, clip01


def donchian_bars(x: Ctx, p: LiteratureParams) -> int:
    """Velas de `donchian_days` días de calendario (24/7) en el marco del contexto."""
    return int(p.donchian_days * 1440 / p.tf_minutes.get(x.timeframe, 60))


def rsi_recross(x: Ctx, p: LiteratureParams, i: int) -> RuleHit | None:
    now, prev = x.rsi[i], x.rsi[i - 1]
    if math.isnan(now) or math.isnan(prev):
        return None
    w = x.rsi[max(0, i - p.rsi_lookback):i]
    if prev < p.rsi_os <= now:
        d, ext, depth = +1, float(w.min()), p.rsi_os - float(w.min())
    elif prev > p.rsi_ob >= now:
        d, ext, depth = -1, float(w.max()), float(w.max()) - p.rsi_ob
    else:
        return None
    s = 0.4 + 0.4 * clip01(depth / 10.0)
    conds = [C(f"RSI({p.rsi_period}) previo → actual", f"{prev:.1f} → {now:.1f}"),
             C("extremo en las últimas velas", round(ext, 1)),
             C("umbral", p.rsi_os if d > 0 else p.rsi_ob)]
    return RuleHit(card_id="murphy_rsi", direction=d, strength=clip01(s),
                   horizon_bars=p.horizon_bars, t=int(x.t[i]), price=float(x.c[i]),
                   timeframe=x.timeframe, conditions=tuple(conds),
                   label="RSI recruza 30 al alza" if d > 0 else "RSI recruza 70 a la baja")


def channel_breakout(x: Ctx, p: LiteratureParams, i: int) -> RuleHit | None:
    n = donchian_bars(x, p)
    if i < n:
        return None
    hi, lo = float(x.h[i - n:i].max()), float(x.lo[i - n:i].min())
    if x.c[i] > hi:
        d, lvl = +1, hi
    elif x.c[i] < lo:
        d, lvl = -1, lo
    else:
        return None
    excess = abs(x.c[i] - lvl) / x.atr[i] if x.atr[i] > 0 else 0.0
    s = 0.5 + 0.5 * clip01(excess / 1.0)
    side = "máx." if d > 0 else "mín."
    conds = [C(f"cierre vs {side} de {p.donchian_days} días", f"{x.c[i]:.2f} vs {lvl:.2f}"),
             C("exceso (ATR)", round(float(excess), 2)), C("velas del canal", n)]
    return RuleHit(card_id="murphy_weekly_rule", direction=d, strength=clip01(s),
                   horizon_bars=p.horizon_bars * 2, t=int(x.t[i]), price=float(x.c[i]),
                   timeframe=x.timeframe, conditions=tuple(conds),
                   label="Ruptura de canal de 4 semanas al alza" if d > 0
                   else "Ruptura de canal de 4 semanas a la baja")
