"""T188: la mitad que sigue corriendo, simulada sobre el camino con orden adverso."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from eim.paper.asym import prereg as P
from eim.paper.asym.runner import run, runner_pairs
from tests.paper.asym.helpers import row

STEP = 15 * 60_000


def path(t0: int, bars: list[tuple[float, float, float, float]]):
    a = np.array(bars, dtype=float)
    return SimpleNamespace(t=np.array([t0 + k * STEP for k in range(len(bars))], dtype=np.int64),
                           o=a[:, 0], h=a[:, 1], l=a[:, 2], c=a[:, 3], step=STEP)


T0 = P.START_MS + 3_600_000


def test_initial_stop_when_it_never_advances():
    p = path(T0, [(100, 100.5, 99.5, 100), (100, 100.2, 98.8, 99)])
    ex = run(p, 1, 100.0, 99.0, T0, P.DAY_MS, 0.1)
    assert ex.reason == "SL" and ex.price == 99.0 and ex.r == pytest.approx(-1.1)


def test_breakeven_then_trailing_one_r_from_the_extreme():
    p = path(T0, [(100, 101.2, 99.8, 101), (101, 103.0, 100.9, 102.8),
                  (102.8, 102.9, 101.5, 101.6)])
    ex = run(p, 1, 100.0, 99.0, T0, P.DAY_MS, 0.1)
    # extremo 103 → stop a 102 (1 R por debajo); la tercera vela lo toca
    assert ex.reason == "STOP" and ex.price == pytest.approx(102.0)
    assert ex.r == pytest.approx(2.0 - 0.1)


def test_adverse_order_inside_a_candle():
    # la misma vela marca extremo nuevo y vuelve al stop vigente: sale el stop, sin moverlo antes
    p = path(T0, [(100, 100.6, 99.6, 100.4), (100.4, 104.0, 98.9, 100)])
    ex = run(p, 1, 100.0, 99.0, T0, P.DAY_MS, 0.0)
    assert ex.price == 99.0


def test_gap_exits_at_the_open():
    p = path(T0, [(100, 100.5, 99.5, 100), (98.0, 98.5, 97.5, 98)])
    assert run(p, 1, 100.0, 99.0, T0, P.DAY_MS, 0.0).price == 98.0


def test_time_limit_exits_at_the_close_and_short_side_mirrors():
    bars = [(100, 100.4, 99.7, 99.9)] * 8
    ex = run(path(T0, bars), -1, 100.0, 101.0, T0, 8 * STEP, 0.0)
    assert ex.reason == "TIEMPO" and ex.r == pytest.approx(0.1)


def test_unfinished_hold_is_not_compared():
    p = path(T0, [(100, 100.4, 99.7, 100)] * 3)
    assert run(p, 1, 100.0, 99.0, T0, P.DAY_MS, 0.0) is None


def test_pairs_mix_half_ladder_half_runner_in_unit_r():
    bars = [(100, 101.2, 99.8, 101), (101, 103.0, 100.9, 102.8), (102.8, 102.9, 101.5, 101.6)]
    r = row(1, r=0.1, weight=0.5, fill=100.0, sl=99.0, fees=0.0, slip=0.0, opened=T0)
    pairs, pending = runner_pairs([r], {"BTCUSDT": path(T0, bars)})
    assert pending == 0
    assert pairs[0].actual == pytest.approx(0.05)
    assert pairs[0].cf == pytest.approx(0.5 * (0.5 * 0.1 + 0.5 * 2.0))
    assert pairs[0].usd_cf > pairs[0].usd_actual
