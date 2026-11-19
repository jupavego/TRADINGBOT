"""Veredictos: tres miradas fijas, mínimos, IC por días y el criterio de T143 en T189."""

from __future__ import annotations

import math

from eim.paper.asym import prereg as P
from eim.paper.asym.verdict import (
    FAIL,
    PASS,
    RUNNING,
    day_block_ci,
    due_look,
    judge_book,
    judge_maker,
)

CP = P.checkpoints_ms()


def test_looks_only_on_their_dates():
    assert due_look(P.START_MS) is None
    assert due_look(CP[0] - 1) is None
    assert due_look(CP[0]) == 0 and due_look(CP[1] + 5) == 1 and due_look(CP[2]) == 2


def test_ci_by_day_blocks():
    pairs = [(d, 0.1 + 0.01 * (d % 3)) for d in range(20) for _ in range(4)]
    m, lo, hi = day_block_ci(pairs)
    assert lo <= m <= hi and lo > 0
    assert day_block_ci([]) == (0.0, -math.inf, math.inf)
    assert day_block_ci([(1, 0.2)])[1] == -math.inf        # un solo día: sin intervalo


def test_no_decision_before_the_first_look():
    v = judge_book([(d, 1.0) for d in range(30) for _ in range(3)], None, "t187b")
    assert v["state"] == RUNNING


def test_pass_needs_minimums_and_ci_above_zero():
    good = [(d, 0.05 + 0.02 * ((d * 7) % 5)) for d in range(20) for _ in range(4)]
    assert judge_book(good, 0, "t187c")["state"] == PASS
    few = good[:30]
    assert judge_book(few, 0, "t187c")["state"] == RUNNING
    assert judge_book(few, 2, "t187c")["state"] == FAIL        # última mirada sin mínimos
    bad = [(d, -x) for d, x in good]
    assert judge_book(bad, 0, "t187c")["state"] == FAIL


def test_noise_around_zero_stays_running_until_the_last_look():
    noise = [(d, (-1) ** (d + k) * 0.3) for d in range(20) for k in range(4)]
    assert judge_book(noise, 0, "t188")["state"] == RUNNING
    assert judge_book(noise, 2, "t188")["state"] == FAIL


def test_maker_needs_cost_drop_and_stable_sign():
    good = [(d, 0.04 + 0.01 * (d % 3)) for d in range(25) for _ in range(10)]
    assert judge_maker(good, 0.05, True, 0, "t189_15m")["state"] == PASS
    assert judge_maker(good, 0.02, True, 0, "t189_15m")["state"] == RUNNING
    assert judge_maker(good, 0.05, False, 2, "t189_15m")["state"] == FAIL
    assert judge_maker(good[:150], 0.05, True, 0, "t189_15m")["state"] == RUNNING
