"""Puerta pura (T49): veredictos, ventanas de ajuste, sin anticipación y Holm."""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.validation.criteria import load_criteria
from eim.validation.gate import (
    OBSERVACION,
    RECHAZADA,
    VALIDADA,
    holm_family,
    measure,
    validate,
    validate_all,
)
from eim.validation.lineage import Window
from tests.validation.helpers import DAY, T0, H, trades, version

CRIT = load_criteria()
FAR = T0 + 10_000 * DAY


def _verdict(ts, windows=(), asof=FAR, attempts=1, prior=None, label="X|s@1h@v1"):
    m = measure(label, ts, windows, "X", asof, CRIT, attempts)
    return validate_all([(version(), m, windows)], prior or {}, CRIT)[0]


def test_clear_edge_is_validated():
    v = _verdict(trades())
    assert v.verdict == VALIDADA, v.reason
    assert all(c.ok for c in v.checks)
    j = v.to_json()
    assert j["id"] == "s@1h@v1" and j["n_oos"] == 220 and j["asof"] == FAR
    assert {c["id"] for c in j["checks"]} == {"V1", "V2", "V3", "V4", "V5", "V6"}
    assert all(c["reason"] and "threshold" in c for c in j["checks"])


@pytest.mark.parametrize("seed", range(8))
def test_random_control_never_validated(seed):
    # control: R sin ventaja (el lado no importa) y costos que se pagan igual
    ts = trades(mean=-0.1, sd=1.0, seed=seed)
    ts = [replace(x, r_flip=-x.r - 0.2) for x in ts]
    v = _verdict(ts)
    assert v.verdict != VALIDADA


def test_insufficient_sample_is_observation():
    v = _verdict(trades(n=60, live_last=0))
    assert v.verdict == OBSERVACION and v.checks[0].ok is False
    assert _verdict([]).verdict == OBSERVACION


def test_live_segment_pending_is_observation():
    v = _verdict(trades(live_last=5))
    assert v.verdict == OBSERVACION and "V5" in v.reason
    assert v.checks[4].ok is None


def test_high_costs_fail_v6():
    v = _verdict(trades(cost=0.5))
    assert v.checks[5].ok is False and v.verdict == RECHAZADA


def test_clearly_negative_is_rejected_even_without_v1():
    v = _verdict(trades(n=40, mean=-0.6, sd=0.8, live_last=0))
    assert v.checks[0].ok is False and v.verdict == RECHAZADA
    assert "claramente negativa" in v.reason


def test_trades_inside_tuning_window_are_excluded():
    ts = trades()
    w = Window(T0, T0 + 60 * DAY, None, "ajuste")
    m = measure("X|s@1h@v1", ts, [w], "X", FAR, CRIT, 1)
    inside = sum(1 for x in ts if w.covers(x.t, "X"))
    assert inside > 0 and m.n == len(ts) - inside and m.excluded == inside
    # una ventana de otro símbolo no excluye nada
    other = measure("X|s@1h@v1", ts, [Window(T0, FAR, "ETHUSDT")], "X", FAR, CRIT, 1)
    assert other.n == len(ts) and other.excluded == 0


def test_verdict_at_t_uses_only_exits_until_t():
    ts = trades()
    cut = ts[150].exit_t
    later = [replace(x, r=-5.0) for x in ts[151:]]      # el futuro es desastroso
    a = measure("X|s@1h@v1", ts[:151] + later, (), "X", cut, CRIT, 1)
    b = measure("X|s@1h@v1", ts[:151], (), "X", cut, CRIT, 1)
    assert a.n == b.n == 151 and a.future == len(later)
    assert a.mean_r == b.mean_r and a.ci == b.ci and a.p_raw == b.p_raw


def test_holm_counts_retired_attempts():
    m = replace(measure("X|s@1h@v1", trades(), (), "X", FAR, CRIT, 1), p_raw=0.01)
    alone = validate_all([(version(), m, ())], {}, CRIT)[0]
    assert alone.checks[2].ok is True and alone.p_holm == pytest.approx(0.01)
    retired = {f"X|s@1h@v{k}": None for k in range(2, 22)}      # 20 intentos retirados
    many = validate_all([(version(), m, ())], retired, CRIT)[0]
    assert many.p_holm == pytest.approx(0.21)
    assert many.checks[2].ok is False and many.verdict == RECHAZADA


def test_holm_family_uses_last_prior_p_and_current_overrides():
    adj = holm_family({"a": 0.01}, {"a": 0.5, "b": 0.02, "c": None})
    assert adj["a"] == pytest.approx(0.03) and adj["c"] == 1.0


def test_null_is_reproducible_and_grows_with_attempts():
    ts = trades(mean=0.15)
    a = measure("X|s@1h@v1", ts, (), "X", FAR, CRIT, 5)
    b = measure("X|s@1h@v1", ts, (), "X", FAR, CRIT, 5)
    assert a.p_raw == b.p_raw and a.ci == b.ci
    assert measure("X|s@1h@v1", ts, (), "X", FAR, CRIT, 100).reps == 4000 and a.reps == 500


def test_drawdown_check():
    ts = trades(mean=-0.05, sd=1.0, n=300, step_h=1, live_last=0)
    ts = [replace(x, r=-1.0) if 50 <= k < 90 else x for k, x in enumerate(ts)]
    m = measure("X|s@1h@v1", ts, (), "X", FAR, CRIT, 1)
    v = validate(version(), m, 0.5, CRIT)
    assert m.dd > 0.25 and v.checks[3].ok is False and v.verdict == RECHAZADA


def test_stability_windows_fail_when_edge_is_one_lucky_month():
    good = trades(n=60, mean=1.5, sd=0.3, step_h=8, live_last=0)
    flat = trades(n=160, mean=-0.15, sd=0.3, step_h=24, seed=3, t0=good[-1].t + 8 * H,
                  live_last=40)
    m = measure("X|s@1h@v1", good + flat, (), "X", FAR, CRIT, 1)
    v = validate(version(), m, 0.001, CRIT)
    assert len(m.windows) >= 4 and v.checks[4].ok is False
