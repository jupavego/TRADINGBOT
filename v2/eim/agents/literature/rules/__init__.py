"""Registro de reglas codificadas: una por ficha de la biblioteca (T52)."""

from __future__ import annotations

from eim.agents.literature.rules import candles as c
from eim.agents.literature.rules import murphy as m
from eim.agents.literature.rules.base import Ctx, RuleHit, RuleSpec


def _tr(p, tf):  # velas mínimas: ATR + tendencia previa
    return max(p.atr_period, p.trend_bars) + 6


RULES: dict[str, RuleSpec] = {s.card_id: s for s in (
    RuleSpec("nison_hammer", c.hammer, _tr),
    RuleSpec("nison_shooting_star", c.shooting_star, _tr),
    RuleSpec("nison_engulfing", c.engulfing, _tr),
    RuleSpec("nison_morning_star", c.morning_star, _tr),
    RuleSpec("nison_evening_star", c.evening_star, _tr),
    RuleSpec("nison_three_white_soldiers", c.three_white_soldiers, _tr),
    RuleSpec("nison_three_black_crows", c.three_black_crows, _tr),
    RuleSpec("murphy_rsi", m.rsi_recross, lambda p, tf: p.rsi_period * 3),
    RuleSpec("murphy_weekly_rule", m.channel_breakout,
             lambda p, tf: p.donchian_days * 1440 // p.tf_minutes.get(tf, 60) + 1),
)}

__all__ = ["RULES", "Ctx", "RuleHit", "RuleSpec"]
