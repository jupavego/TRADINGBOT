"""Cada regla dispara con su patrón sintético y no dispara sin él."""
from __future__ import annotations

import pytest

from eim.agents.literature import LiteratureAgent
from tests.agents.literature._synth import flat, ohlc, snap, trend

DOWN, UP = trend(-1), trend(+1)


def active(bars: list[tuple], tf: str = "1h") -> dict[str, int]:
    rep = LiteratureAgent().run(snap(bars, tf))
    return {h["card_id"]: h["direction"] for h in rep.metrics.get("hits", [])}


def last(bars: list[tuple]) -> float:
    return bars[-1][3]


def test_hammer_fires_after_decline_only():
    p = last(DOWN)
    hammer = ohlc(p - 0.1, p + 0.1, up=0.01, dn=0.7)
    assert active(DOWN + [hammer]).get("nison_hammer") == 1
    assert "nison_hammer" not in active(UP + [ohlc(last(UP) - 0.1, last(UP) + 0.1, 0.01, 0.7)])
    assert "nison_hammer" not in active(DOWN + [ohlc(p - 0.1, p + 0.1, 0.01, 0.1)])


def test_shooting_star_fires_after_advance_only():
    p = last(UP)
    star = ohlc(p + 0.1, p - 0.1, up=0.7, dn=0.01)
    assert active(UP + [star]).get("nison_shooting_star") == -1
    assert "nison_shooting_star" not in active(DOWN + [ohlc(last(DOWN) + 0.1, last(DOWN) - 0.1,
                                                            0.7, 0.01)])


def test_engulfing_both_sides_and_not_without_trend():
    p = last(DOWN)
    bull = [ohlc(p, p - 0.3), ohlc(p - 0.4, p + 1.0)]
    assert active(DOWN + bull).get("nison_engulfing") == 1
    q = last(UP)
    bear = [ohlc(q, q + 0.3), ohlc(q + 0.4, q - 1.0)]
    assert active(UP + bear).get("nison_engulfing") == -1
    assert "nison_engulfing" not in active(flat() + [ohlc(1000, 999.8), ohlc(999.7, 1001)])


def test_morning_and_evening_star():
    p = last(DOWN)
    morning = [ohlc(p, p - 2.5), ohlc(p - 2.9, p - 2.8), ohlc(p - 2.7, p - 0.2)]
    assert active(DOWN + morning).get("nison_morning_star") == 1
    q = last(UP)
    evening = [ohlc(q, q + 2.5), ohlc(q + 2.9, q + 2.8), ohlc(q + 2.7, q + 0.2)]
    assert active(UP + evening).get("nison_evening_star") == -1
    weak = [ohlc(p, p - 2.5), ohlc(p - 2.9, p - 2.8), ohlc(p - 2.7, p - 2.5)]
    assert "nison_morning_star" not in active(DOWN + weak)


def test_three_soldiers_from_low_zone_and_crows_from_high():
    base = flat()
    p = 1000.0
    soldiers = [ohlc(p, p + 1.5, 0.05, 0.05), ohlc(p + 0.8, p + 3.0, 0.05, 0.05),
                ohlc(p + 2.3, p + 4.5, 0.05, 0.05)]
    assert active(base + soldiers).get("nison_three_white_soldiers") == 1
    q = last(UP)
    crows = [ohlc(q, q - 1.5, 0.05, 0.05), ohlc(q - 0.8, q - 3.0, 0.05, 0.05),
             ohlc(q - 2.3, q - 4.5, 0.05, 0.05)]
    assert active(UP + crows).get("nison_three_black_crows") == -1
    # bloque de avance (cuerpos decrecientes): no se compra
    block = [ohlc(p, p + 2.5, 0.05, 0.05), ohlc(p + 1.5, p + 3.5, 0.05, 0.05),
             ohlc(p + 2.8, p + 4.2, 0.05, 0.05)]
    assert "nison_three_white_soldiers" not in active(base + block)


def test_rsi_recross_30_and_70():
    rebound = DOWN + trend(+1, n=1, start=last(DOWN), step=3.0)
    assert active(rebound).get("murphy_rsi") == 1
    drop = UP + trend(-1, n=1, start=last(UP), step=3.0)
    assert active(drop).get("murphy_rsi") == -1
    assert "murphy_rsi" not in active(flat())


def test_channel_breakout_four_weeks():
    base = flat(n=700)                         # 28 d en 1 h = 672 velas
    up = [ohlc(1000, 1003, 0.1, 0.1)]
    assert active(base + up).get("murphy_weekly_rule") == 1
    assert active(base + [ohlc(1000, 997, 0.1, 0.1)]).get("murphy_weekly_rule") == -1
    assert "murphy_weekly_rule" not in active(base + [ohlc(1000, 1000.3)])


@pytest.mark.parametrize("tf", ["15m", "1h", "4h", "1d"])
def test_degraded_when_history_too_short_for_channel(tf):
    rep = LiteratureAgent().run(snap(DOWN + [ohlc(last(DOWN), last(DOWN) - 0.1)], tf))
    assert rep.status in {"degraded", "ok"}
    if rep.status == "degraded":
        assert any("murphy_weekly_rule" in w for w in rep.warnings)
