"""T214: potencia a priori (aritmética anterior a cualquier resultado)."""

from __future__ import annotations

import math
from datetime import date

import pytest

from eim.options import surface_power as sp


def test_days_needed_is_the_t163_formula_with_holm():
    z = sp.z_holm(1141)
    assert z == pytest.approx(4.764, abs=1e-3)
    d = sp.delta_min()
    assert d == pytest.approx(0.014725)
    assert sp.days_needed(0.2405, d, 1141) == pytest.approx((z * 0.2405 / d) ** 2)
    assert sp.days_needed(0.2405, d, 1141, kappa=2.0) == pytest.approx(
        2 * sp.days_needed(0.2405, d, 1141))


def test_binding_case_does_not_fit_before_the_cap():
    fam = sp.FAMILY_T95 + sp.N_ATTEMPTS
    n = sp.days_needed(sp.S_CENTRAL, sp.delta_min(), fam)
    assert 6000 < n < 6100
    assert sp.first_evaluation(n) > sp.CAP
    assert sp.max_s_for_cap(sp.delta_min(), fam) == pytest.approx(0.0898, abs=5e-4)
    assert min(sp.S_PRIOR.values()) > sp.max_s_for_cap(sp.delta_min(), fam)


def test_first_evaluation_counts_warmup_and_valid_rate():
    assert sp.first_evaluation(0) == date(2026, 11, 28).fromordinal(
        date(2026, 11, 28).toordinal() + 250)
    assert sp.first_evaluation(100, valid_rate=0.5) == date.fromordinal(
        date(2026, 11, 28).toordinal() + 700)
    assert sp.first_evaluation(math.inf) is None


def test_power_table_is_monotone_in_s_family_and_delta():
    rows = sp.power_table()
    assert len(rows) == 3 * 2 * 3
    by = {(r.s, r.family, r.rel): r.days for r in rows}
    for s in sp.S_PRIOR.values():
        assert by[(s, 3, 0.05)] < by[(s, 1141, 0.05)]
        assert by[(s, 1141, 0.10)] < by[(s, 1141, 0.05)] < by[(s, 1141, 0.03)]
    assert all(not r.before_cap for r in rows if r.family == 1141 and r.rel == 0.05)
    assert rows[0].to_json()["days_scored"] == math.ceil(rows[0].days)
