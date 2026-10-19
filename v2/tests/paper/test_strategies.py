"""Catálogo de estrategias: sin anticipación, determinismo y forma de las ideas (T47)."""

from __future__ import annotations

import math

import numpy as np

from eim.core import Candle
from eim.paper.catalog import CATALOG, generate_ideas
from eim.paper.ideas import Draft, to_idea
from eim.paper.params import FAMILIES
from eim.paper.strategies import control_aleatorio
from tests.paper.helpers import H1, T0


def walk(n: int, seed: int = 7, t0: int = T0) -> list[Candle]:
    rng = np.random.default_rng(seed)
    p, out = 100.0, []
    for i in range(n):
        o = p
        p = p * math.exp(rng.normal(0, 0.01))
        hi, lo = max(o, p) * 1.003, min(o, p) * 0.997
        out.append(Candle(t=t0 + i * H1, o=o, h=hi, l=lo, c=p, v=100.0))
    return out


def ctx_for(c: Candle, bias: float = 0.4) -> dict:
    return {
        "v": 1, "t": c.t + H1, "close": c.c, "atr": c.c * 0.01, "sigma_h": c.c * 0.005,
        "agents": {"levels": [bias, 0.5, "ok"], "vwap": [-bias, 0.5, "ok"]}, "regime": "range",
        "syn": {"bias": bias, "conf": 0.4, "agree": 0.7},
        "plan": {"side": "long", "entry": c.c, "sl": c.c * 0.98, "tp": [c.c * 1.03, c.c * 1.05],
                 "rr": 1.5, "status": "VIGENTE", "created_t": c.t, "conf": 0.6},
        "setups": [{"side": "long", "entry": c.c * 0.995, "sl": c.c * 0.985, "tp": c.c * 1.02,
                    "rr": 2.5, "p_fill": 0.7, "p_tp": 0.4, "ev_r": 0.3, "hours": 10,
                    "aligned": True, "conf_n": 2, "basis": "test"}],
        "fc": {"h": 24, "bull": {"p": 0.5, "end": c.c * 1.02, "lo": c.c, "hi": c.c * 1.04,
                                 "inv": c.c * 0.99, "inv_low": None},
               "neutral": {"p": 0.3, "end": c.c, "lo": c.c * 0.99, "hi": c.c * 1.01,
                           "inv": None, "inv_low": None},
               "bear": {"p": 0.2, "end": c.c * 0.98, "lo": c.c * 0.96, "hi": c.c,
                        "inv": c.c * 1.01, "inv_low": None},
               "q": {"10": c.c * 0.97, "25": c.c * 0.985, "50": c.c, "75": c.c * 1.015,
                     "90": c.c * 1.03}},
    }


def test_no_lookahead_in_ideas():
    cs = walk(700)
    ctxs = [ctx_for(cs[i]) for i in range(450, 600)]
    base = generate_ideas(ctxs, cs, "X", H1)
    cut = 520                                   # contexto con t = cierre de la vela 520
    altered = cs[:cut + 1] + [Candle(t=c.t, o=c.o * 3, h=c.h * 3, l=c.l * 3, c=c.c * 3, v=1)
                              for c in cs[cut + 1:]]
    again = generate_ideas(ctxs, altered, "X", H1)
    t_cut = cs[cut].t + H1
    assert [i for i in base if i.t <= t_cut] == [i for i in again if i.t <= t_cut]
    assert any(i.family == "indicadores" for i in base if i.t <= t_cut)


def test_all_families_and_shapes():
    cs = walk(700)
    ideas = generate_ideas([ctx_for(cs[i]) for i in range(450, 700)], cs, "X", H1)
    fams = {i.family for i in ideas}
    assert {"consenso", "sugerencias", "escenarios", "agentes", "contrarias",
            "control"} <= fams <= set(FAMILIES)
    for i in ideas:
        assert (i.entry - i.sl) * i.side > 0 and (i.tp - i.entry) * i.side > 0
        assert (i.kind == "limit") == (i.fill_ms > 0) and i.hold_ms > 0
    sug = [i for i in ideas if i.strategy == "sugerencia_1"]
    assert sug and all(i.kind == "limit" and i.fill_ms == 12 * H1 for i in sug)
    plan = [i for i in ideas if i.strategy == "plan_tp1"]
    assert plan and all(i.key.startswith("plan:") for i in plan)
    assert len(CATALOG) >= 25


def test_contrarian_is_opposite():
    cs = walk(600)
    ideas = generate_ideas([ctx_for(cs[500], bias=0.5)], cs, "X", H1)
    by = {i.strategy: i for i in ideas}
    assert by["consenso_sintesis"].side == -by["contra_sintesis"].side == 1


def test_control_is_deterministic_and_sparse():
    picks = [control_aleatorio({"t": T0 + k * H1, "symbol": "X", "close": 100, "atr": 1}, None, 0)
             for k in range(2000)]
    again = [control_aleatorio({"t": T0 + k * H1, "symbol": "X", "close": 100, "atr": 1}, None, 0)
             for k in range(2000)]
    assert picks == again
    rate = sum(p is not None for p in picks) / len(picks)
    assert 0.15 < rate < 0.25
    sides = [p.side for p in picks if p]
    assert 0.35 < sides.count(1) / len(sides) < 0.65


def test_bad_geometry_dropped():
    info = CATALOG["consenso_sintesis"]
    d = Draft(side=1, sl=101, tp=105, conf=0.5, why=("x",), entry=100)
    assert to_idea(info, d, {"t": T0, "close": 100}, "X", "backtest") is None


def test_base_follows_higher_timeframe_trend_every_bar():
    """«Posición base»: una idea por vela, a favor de la tendencia mayor, con salidas anchas;
    sin tendencia conocida no opera."""
    cs = walk(600)
    up = generate_ideas([ctx_for(cs[i]) for i in range(500, 520)], cs, "X", H1, htf=lambda _t: 1)
    base = [i for i in up if i.strategy == "base_tendencia"]
    assert len(base) == 20 and all(i.side == 1 and i.htf == 1 and i.family == "base" for i in base)
    assert all(abs(abs(i.tp - i.entry) / abs(i.entry - i.sl) - 1.5) < 1e-9 for i in base)
    down = generate_ideas([ctx_for(cs[510])], cs, "X", H1, htf=lambda _t: -1)
    assert [i.side for i in down if i.strategy == "base_tendencia"] == [-1]
    none = generate_ideas([ctx_for(cs[510])], cs, "X", H1)
    assert not [i for i in none if i.strategy == "base_tendencia"]
