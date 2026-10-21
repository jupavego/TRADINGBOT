"""Aporte marginal (regla fijada de antemano) y degradación de bots (T59), sin red."""

from __future__ import annotations

import numpy as np
import pandas as pd

from eim.bots.concept import INFORMA, VOTA, assign
from eim.bots.health import HealthParams, assess, conditions, drift_agreement
from eim.bots.marginal import DUP_RHO, decide, measured_weight, moderator_effect
from eim.bots.scorecard import score
from eim.core import Candle
from eim.operation.alerts import WARN
from tests.bots.score_helpers import CRIT, SYMBOL, T0, H, Market, card, oracle_rows, signal, version

NAME = "bot:x"


def result(d_sharpe=0.5, d_exp=0.05, d_ic=0.01, win=0.8, rho=None, cov=0.2, n_win=4) -> dict:
    """Salida mínima de `agents_marginal.evaluate` para un bot `NAME`."""
    def row(sh, ex, ic):
        return {"metrics": {"sharpe": sh, "expectancy_r": ex},
                "ic": [{"delta": None}, {"delta": ic}], "vs_base": {"win_share": win},
                "windows": [{}] * n_win}
    corr = {f"{NAME}~{p}": {"pearson": rho.get(p) if rho else None}
            for p in ("ema", "structure", "technical")}
    return {"coverage": {NAME: {"ok": 1.0 - cov, "no_data": cov}}, "corr_disc": corr,
            "variants": {"base": row(1.0, 0.1, 0.0), f"+{NAME}": row(1.0 + d_sharpe, 0.1 + d_exp,
                                                                      d_ic)}}


def test_information_distinct_from_core_votes_with_small_weight():
    m = decide(result(rho={"ema": 0.1, "structure": 0.2, "technical": 0.05}), NAME)
    assert m.contributes and 0 < m.weight < 0.5 and m.weight == measured_weight(0.2)


def test_duplicate_of_core_has_zero_weight_even_if_it_improves():
    m = decide(result(rho={"ema": DUP_RHO + 0.05}), NAME)
    assert not m.contributes and m.weight == 0.0 and "repite" in m.reason


def test_single_window_is_not_evidence():
    m = decide(result(win=1.0, n_win=1, rho={"ema": 0.1}), NAME)
    assert not m.contributes and m.weight == 0.0 and "no medible" in m.reason


def test_no_improvement_means_zero_weight():
    m = decide(result(d_sharpe=-0.1, d_ic=-0.01, rho={"ema": 0.2}), NAME)
    assert not m.contributes and m.weight == 0.0


def test_unmeasurable_bot_is_not_decreed():
    m = decide(result(cov=1.0), NAME)
    assert not m.contributes and m.weight == 0.0


def _moderated(agree_hit: float, disagree_hit: float, n: int = 1000):
    """Núcleo aleatorio y precio construido para que acierte `agree_hit` cuando el bot coincide
    y `disagree_hit` cuando no. Muestras cada 24 velas (sin solape)."""
    rng = np.random.default_rng(1)
    asofs = [T0 + k * 4 * H for k in range(n)]
    sign = rng.choice([-1.0, 1.0], n)
    agree = rng.random(n) < 0.5
    stance = {a: float(s if ag else -s) for a, s, ag in zip(asofs, sign, agree, strict=True)}
    close = np.full(n * 4 + 40, 100.0)
    level = 100.0
    for k in range(0, n, 6):
        hit = rng.random() < (agree_hit if agree[k] else disagree_hit)
        level *= float(np.exp(0.01 * sign[k] * (1 if hit else -1)))
        close[4 * k - 1 + 24:] = level
        close[4 * k - 1:4 * k - 1 + 24] = close[4 * k - 1]
    candles = [Candle(t=T0 + i * H, o=c, h=c, l=c, c=c, v=1.0) for i, c in enumerate(close)]
    return pd.Series(sign, index=asofs), stance, candles, asofs[0]


def test_moderator_detects_a_clear_gap_and_ignores_noise():
    core, stance, candles, cut = _moderated(0.8, 0.3)
    assert moderator_effect(core, stance, candles, cut)["modulates"] is True
    core, stance, candles, cut = _moderated(0.5, 0.5)
    assert moderator_effect(core, stance, candles, cut)["modulates"] is False


def test_moderator_needs_enough_sample():
    core, stance, candles, cut = _moderated(0.8, 0.3, n=120)
    out = moderator_effect(core, stance, candles, cut)
    assert out["modulates"] is False and "insuficiente" in out["note"]


def test_degradation_rules():
    ok = [signal(T0 + k * H, 1.0) for k in range(100)]
    assert not assess([0.3] * 30, 0.0, ok).degraded
    live = assess([-0.2] * 30, 0.05, ok)
    assert live.degraded and "rendimiento vivo" in live.reasons[0]
    assert not assess([-0.2] * 10, 0.05, ok).degraded            # muestra viva insuficiente
    bad = [signal(T0 + k * H, 0.0, status="degraded") for k in range(20)] + ok[:80]
    assert "fallos del ejecutor" in assess([], None, bad).reasons[0]
    old = [signal(T0 + k * H, 1.0, ver=version("1")) for k in range(80)]
    new = [signal(T0 + k * H, -1.0, ver=version("2")) for k in range(80)]
    assert drift_agreement(old, new) == (0.0, 80)
    assert "deriva" in assess([], None, new, old, new).reasons[0]
    assert assess([], None, ok, p=HealthParams(fail_max=0.5)).degraded is False


def test_alert_condition_follows_t31_pattern():
    h = assess([-0.2] * 30, 0.05, [])
    (c,) = conditions("b:s@1h@v1", h)
    assert c.on and c.level == WARN and c.kind == "bot_degradado"
    assert not conditions("b:s@1h@v1", assess([], None, []))[0].on


def test_degraded_voter_drops_to_informs():
    m = Market(days=140)
    rows = oracle_rows(m)
    from eim.bots.marginal import Marginal
    good = Marginal(True, 0.25, "aporta", 0.2)
    out = score(rows, m.c1h, m.path, SYMBOL, CRIT, {"hummingbot-directional": card()}, m.end,
                m.regime_at, {"hummingbot-directional:s1@1h@v1": good})
    v = out["bots"][0]["verdict"]
    # El oráculo sintético tiene R casi constante (IC ≈ un punto): su rendimiento vivo puede quedar
    # una milésima bajo el límite y degradar solo; el estado sano se fija con una salud sin motivos.
    ok = assign("l", ("hummingbot-directional", "s1", "1h", version()), card(), v, good,
                assess([], None, []))
    assert ok.state == VOTA and ok.weight == 0.25
    h = assess([-1.0] * 30, 0.0, [], )
    c = assign("l", ("hummingbot-directional", "s1", "1h", version()), card(), v, good, h)
    assert c.state == INFORMA and c.weight == 0.0 and any("degradación" in r for r in c.reasons)
