"""T132 — las candidatas como `ExitPolicy`: M2, M3, M5, M6, M7, S1 y M8.

Lo que se comprueba de cada una es su **mecanismo propio**, no que gane: elegir ganadora es T134.
Y de las dos que cambian el SL inicial (S1 y M8), que lo aparten **solo hacia fuera** y que sin
dato no toquen nada.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.paper.exits import features
from eim.paper.exits.candidates import (
    HtfExit,
    InitialStopExit,
    TimeExit,
    TrailExit,
    sigma_floor,
    widen_stop,
)
from eim.paper.exits.policy import ExitPolicy
from eim.paper.exits.rules import BREAK_EVEN, SURVIVAL, TRAIL
from tests.paper.exits.helpers import SPEC, ZERO, coherent_path, ctx
from tests.paper.helpers import idea

QTY = 0.01
SIG = "parkinson"


@pytest.fixture(scope="module")
def world():
    p, fine = coherent_path(400, seed=77)
    return p, fine, features.build(p, SIG, swing_bars=5)


def m2(f, k=2.0, activate=0.0, floor_n=0.0) -> TrailExit:
    from eim.paper.exits.trail import TrailLimits
    return TrailExit("M2", "M2 chandelier", f, "M2", {"k": k, "activate_r": activate},
                     TrailLimits(floor_n=floor_n))


def test_every_candidate_satisfies_the_exit_policy_protocol(world):
    p, fine, f = world
    pols = [m2(f), TrailExit("M3", "M3", f, "M3", {"buffer_sigma": 0.25}),
            TrailExit("M5", "M5", f, "M5",
                      {"k": 2.0, "survival_r": 0.3, "a_r": 1.0, "b_r": 0.1, "trail": "M2"}),
            TimeExit("M6", "M6", f, bars=16, min_r=0.5),
            HtfExit("M7", "M7", f),
            InitialStopExit("S1", "S1", "S1", f, sigma_floor(f, p.t, 2.0))]
    for pol in pols:
        assert isinstance(pol, ExitPolicy), pol.id
        assert pol.params["policy"] in {"M2", "M3", "M5", "M6", "M7", "S1"}


def test_m2_does_not_move_the_stop_before_its_activation(world):
    p, fine, f = world
    px = float(p.c[1])
    i = idea(entry=px, sl=px * 0.99, tp=px * 1.2, t=int(p.t[1]) + p.step)
    never = m2(f, k=2.0, activate=99.0).simulate(i, ctx(p, ZERO, fine), QTY)
    assert never.ladder["stop_history"] == []
    always = m2(f, k=2.0, activate=0.0).simulate(i, ctx(p, ZERO, fine), QTY)
    assert len(always.ladder["stop_history"]) >= 1


def test_m3_anchors_on_a_confirmed_swing_and_nothing_else(world):
    p, fine, f = world
    px = float(p.c[1])
    i = idea(entry=px, sl=px * 0.99, tp=px * 1.2, t=int(p.t[1]) + p.step)
    o = TrailExit("M3", "M3", f, "M3", {"buffer_sigma": 0.0}).simulate(i, ctx(p, ZERO, fine), QTY)
    for h in o.ladder["stop_history"]:
        j = h["bar"]
        assert h["stop"] == pytest.approx(float(f.swing_low[j]), abs=SPEC.tick)


def test_m3_without_swings_proposes_nothing(world):
    p, fine, f = world
    bare = features.build(p, SIG, swing_bars=5)
    empty = type(bare)(**{**bare.__dict__, "swing_low": np.full(len(p.t), np.nan),
                          "swing_high": np.full(len(p.t), np.nan)})
    px = float(p.c[1])
    i = idea(entry=px, sl=px * 0.99, tp=px * 1.2, t=int(p.t[1]) + p.step)
    o = TrailExit("M3", "M3", empty, "M3", {}).simulate(i, ctx(p, ZERO, fine), QTY)
    assert o.ladder["stop_history"] == []


def test_m5_goes_through_its_phases_in_order_and_never_mixes_two_stops(world):
    p, fine, f = world
    px = float(p.c[1])
    i = idea(entry=px, sl=px * 0.99, tp=px * 1.3, t=int(p.t[1]) + p.step)
    pol = TrailExit("M5", "M5", f, "M5",
                    {"k": 2.0, "survival_r": 0.5, "a_r": 1.0, "b_r": 0.1, "trail": "M2"})
    o = pol.simulate(i, ctx(p, ZERO, fine), QTY)
    phases = [h["phase"] for h in o.ladder["stop_history"]]
    assert all(x in (BREAK_EVEN, TRAIL) for x in phases), phases
    assert SURVIVAL not in phases, "en supervivencia el stop no se mueve"
    seen_trail = False
    for x in phases:                                   # una vez en arrastre, no se vuelve al BE+
        seen_trail = seen_trail or x == TRAIL
        assert not (seen_trail and x == BREAK_EVEN)


def test_m6_closes_at_the_open_of_its_bar_when_the_advance_fell_short(world):
    p, fine, f = world
    px = float(p.c[1])
    i = idea(entry=px, sl=px * 0.97, tp=px * 1.3, t=int(p.t[1]) + p.step, hold_h=1000)
    o = TimeExit("M6", "M6", f, bars=10, min_r=99.0).simulate(i, ctx(p, ZERO, fine), QTY)
    assert o.reason == "TIEMPO"
    j = int(np.searchsorted(p.t, o.exit_t))
    assert o.exit == pytest.approx(float(p.o[j]))      # a la apertura de su vela
    assert o.ladder["bars"] <= 10


def test_m6_does_not_close_what_already_advanced_enough(world):
    p, fine, f = world
    px = float(p.c[1])
    i = idea(entry=px, sl=px * 0.97, tp=px * 1.3, t=int(p.t[1]) + p.step, hold_h=1000)
    o = TimeExit("M6", "M6", f, bars=10, min_r=0.0).simulate(i, ctx(p, ZERO, fine), QTY)
    assert o.reason != "TIEMPO"


def test_m7_only_closes_when_the_higher_timeframe_flips(world):
    p, fine, f = world
    px = float(p.c[1])
    i = idea(entry=px, sl=px * 0.97, tp=px * 1.3, t=int(p.t[1]) + p.step, hold_h=1000)
    o = HtfExit("M7", "M7", f).simulate(i, ctx(p, ZERO, fine), QTY)
    if o.reason == "HTF":
        j = int(np.searchsorted(p.t, o.exit_t))
        entry_j = int(np.searchsorted(p.t, i.t))
        assert int(f.htf_dir[j]) != int(f.htf_dir[entry_j]) != 0


def test_m7_with_no_trend_data_never_closes_by_reversal(world):
    p, fine, f = world
    flat = type(f)(**{**f.__dict__, "htf_dir": np.zeros(len(p.t), dtype=np.int8)})
    px = float(p.c[1])
    i = idea(entry=px, sl=px * 0.97, tp=px * 1.3, t=int(p.t[1]) + p.step, hold_h=1000)
    assert HtfExit("M7", "M7", flat).simulate(i, ctx(p, ZERO, fine), QTY).reason != "HTF"


# --- S1 y M8: el SL inicial ---------------------------------------------------------------
def test_widening_the_stop_only_goes_outwards():
    i = idea(entry=100.0, sl=99.0)                     # distancia 1,0
    assert widen_stop(i, 2.0, 0.1).sl == pytest.approx(98.0)       # se aparta
    assert widen_stop(i, 0.5, 0.1).sl == pytest.approx(99.0)       # NO se acerca
    assert widen_stop(i, None, 0.1).sl == pytest.approx(99.0)      # sin dato, no toca
    assert widen_stop(i, float("nan"), 0.1).sl == pytest.approx(99.0)
    short = idea(side=-1, entry=100.0, sl=101.0, tp=96.0)
    assert widen_stop(short, 2.0, 0.1).sl == pytest.approx(102.0)  # el corto, hacia arriba


def test_s1_widens_the_stop_by_sigma_and_keeps_the_risk_in_r(world):
    p, fine, f = world
    px = float(p.c[200])
    t = int(p.t[200]) + p.step
    i = idea(entry=px, sl=px * 0.9995, tp=px * 1.1, t=t)           # SL pegadísimo
    pol = InitialStopExit("S1", "S1", "S1", f, sigma_floor(f, p.t, 3.0))
    o = pol.simulate(i, ctx(p, ZERO, fine), QTY)
    sig = float(f.sigma_abs[200])
    assert np.isfinite(sig) and sig > 0
    assert abs(px - o.ladder["initial_sl"]) >= 3.0 * sig - SPEC.tick
    assert o.r is None or abs(o.r) <= 1.0 + 1e-9       # sigue siendo 1 R de riesgo


def test_s1_without_sigma_leaves_the_idea_untouched(world):
    p, fine, f = world
    nan_f = type(f)(**{**f.__dict__, "sigma_abs": np.full(len(p.t), np.nan)})
    px = float(p.c[200])
    i = idea(entry=px, sl=px * 0.999, tp=px * 1.1, t=int(p.t[200]) + p.step)
    o = InitialStopExit("S1", "S1", "S1", nan_f, sigma_floor(nan_f, p.t, 3.0)).simulate(
        i, ctx(p, ZERO, fine), QTY)
    assert o.ladder["initial_sl"] == pytest.approx(i.sl)


def test_an_initial_stop_policy_can_delegate_the_trail_to_another_one(world):
    p, fine, f = world
    px = float(p.c[200])
    i = idea(entry=px, sl=px * 0.999, tp=px * 1.2, t=int(p.t[200]) + p.step)
    pol = InitialStopExit("S1+M2", "S1 con M2", "S1", f, sigma_floor(f, p.t, 2.0),
                          inner=m2(f, k=2.0))
    o = pol.simulate(i, ctx(p, ZERO, fine), QTY)
    assert o.ladder["rule"] == "M2"                    # el arrastre lo llevó la interna
    assert o.ladder["initial_sl"] != pytest.approx(i.sl)
    assert pol.params["inner"]["policy"] == "M2"
