"""T134 — los ocho criterios de §5.4: que aprueben solo lo que cumple y digan qué falla.

Lo que se vigila aquí es que no haya atajos: que un «no se pudo medir» quede **pendiente** y no
aprobado, que fallar frente a UNA base baste para rechazar, y que el criterio 7 sea siempre
pendiente porque su dato no existe hasta T135.
"""

from __future__ import annotations

from eim.paper.exits import verdict as vd
from eim.paper.exits.prereg import load_prereg

ACCEPT = load_prereg().accept
BASES = {"M0": {"pf": 0.39, "max_dd_r": 4591.0, "cvar95_r": -1.350},
         "M1": {"pf": 0.73, "max_dd_r": 4560.0, "cvar95_r": -1.394}}
GOOD_M = {"win_loss_ratio": 0.9, "pf": 1.2, "max_dd_r": 3000.0, "cvar95_r": -1.20}
GOOD_D = {"M0": {"delta": 0.05, "ci": [0.02, 0.08], "p_rw": 0.01},
          "M1": {"delta": 0.04, "ci": [0.01, 0.07], "p_rw": 0.02}}


def judge(**kw):
    args = {"variant": "X", "family": "M2", "m": GOOD_M, "bases": BASES, "deltas": GOOD_D,
            "fold_deltas": [0.05] * 10, "years": {str(y): 0.04 for y in (2023, 2024, 2025, 2026)},
            "plateau": True, "pbo": 0.1, "control": {"ok": True, "reason": "p=0,4"},
            "stress": GOOD_D, "accept": ACCEPT}
    return vd.judge(**{**args, **kw})


def test_everything_measurable_right_makes_it_a_candidate_not_approved():
    """T134 no puede aprobar nada: el criterio 7 es prospectivo y su dato nace en T135."""
    got = judge()
    assert got.status == vd.CANDIDATE
    assert [c.ok for c in got.checks] == [True, True, True, True, True, True, None, True]
    assert "prospectivo" in got.reason


def test_criterion_7_is_always_pending_here():
    """Su dato no existe hasta T135: no puede contar como cumplido."""
    c7 = next(c for c in judge().checks if c.n == 7)
    assert c7.ok is None and "T135" in c7.value
    assert judge().status != vd.APPROVED       # nada se aprueba en T134


def test_pending_something_else_is_not_the_same_as_being_a_candidate():
    assert judge(control=None).status == vd.PENDING
    assert judge().status == vd.CANDIDATE


def test_failing_against_only_one_base_is_enough_to_reject():
    half = {"M0": GOOD_D["M0"], "M1": {"delta": -0.01, "ci": [-0.04, 0.02], "p_rw": 0.9}}
    got = judge(deltas=half)
    assert got.status == vd.REJECTED and "criterio 1" in got.reason


def test_a_positive_delta_with_an_interval_touching_zero_fails():
    weak = {"M0": {"delta": 0.05, "ci": [-0.001, 0.1], "p_rw": 0.01}, "M1": GOOD_D["M1"]}
    assert judge(deltas=weak).status == vd.REJECTED


def test_a_delta_that_does_not_survive_the_correction_fails():
    raw_only = {"M0": {"delta": 0.05, "ci": [0.02, 0.08], "p_rw": 0.20}, "M1": GOOD_D["M1"]}
    assert judge(deltas=raw_only).status == vd.REJECTED


def test_the_profit_factor_is_compared_against_the_worst_base_times_the_margin():
    c2 = next(c for c in judge(m={**GOOD_M, "pf": 0.80}).checks if c.n == 2)
    assert c2.ok is False                       # 0,80 < 1,15 × 0,73 = 0,84
    ok = next(c for c in judge(m={**GOOD_M, "pf": 0.90}).checks if c.n == 2)
    assert ok.ok is True


def test_the_win_loss_ratio_floor_is_applied():
    assert next(c for c in judge(m={**GOOD_M, "win_loss_ratio": 0.4}).checks
                if c.n == 2).ok is False


def test_a_worse_tail_than_the_best_base_fails_even_with_a_better_drawdown():
    c3 = next(c for c in judge(m={**GOOD_M, "cvar95_r": -1.40}).checks if c.n == 3)
    assert c3.ok is False and "CVaR" in c3.value


def test_a_drawdown_above_the_margin_fails():
    assert next(c for c in judge(m={**GOOD_M, "max_dd_r": 6000.0}).checks if c.n == 3).ok is False


def test_a_single_negative_year_fails_the_fourth_criterion():
    bad = {"2023": 0.04, "2024": -0.01, "2025": 0.03, "2026": 0.02}
    c4 = next(c for c in judge(years=bad).checks if c.n == 4)
    assert c4.ok is False and "2024" in c4.value


def test_too_few_positive_folds_fails():
    folds = [0.05] * 5 + [-0.02] * 5
    assert next(c for c in judge(fold_deltas=folds).checks if c.n == 4).ok is False


def test_the_pbo_limit_is_applied_even_with_a_plateau():
    assert next(c for c in judge(pbo=0.45).checks if c.n == 5).ok is False
    assert next(c for c in judge(plateau=False).checks if c.n == 5).ok is False


def test_a_control_that_stands_out_from_the_null_rejects():
    got = judge(control={"ok": False, "reason": "p=0,01"})
    assert got.status == vd.REJECTED and "criterio 6" in got.reason


def test_what_could_not_be_measured_stays_pending_and_is_not_approved():
    got = judge(control=None, stress=None)
    assert got.status == vd.PENDING
    assert "criterio 6" in got.reason and "8" in got.reason
    assert next(c for c in got.checks if c.n == 8).value.startswith("no se midió")


def test_the_eighth_criterion_is_the_first_one_with_stressed_costs():
    worse = {"M0": {"delta": 0.001, "ci": [-0.01, 0.02], "p_rw": 0.4},
             "M1": {"delta": 0.001, "ci": [-0.01, 0.02], "p_rw": 0.4}}
    got = judge(stress=worse)
    assert got.status == vd.REJECTED and "criterio 8" in got.reason
    c8 = next(c for c in got.checks if c.n == 8)
    assert c8.n == 8 and c8.ok is False


def test_the_verdict_serialises_with_every_criterion_named():
    j = judge().to_json()
    assert [c["n"] for c in j["checks"]] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert all(c["name"] for c in j["checks"])
    assert j["status"] == vd.CANDIDATE and j["variant"] == "X"
