"""T135 — La potencia del A/B (E9): las cuentas, y un plan que no se reescribe después."""

from __future__ import annotations

import json

import pytest

from eim.paper.exits.power import (
    MIN_WEEKS,
    fingerprint,
    inputs_from_report,
    min_detectable,
    power_plan,
    required_n,
    write_plan,
)

SD_T134 = 0.3517305204407376           # `M8 q=0.95` − M0, de `reports/exits_ab.json`
EFFECT_T134 = 0.0493


def plan(**kw):
    args = {"candidate": "M2 k=3", "base": "M0", "sd": SD_T134, "effect": EFFECT_T134,
            "trades_per_week": 40.0, "source": "prueba"} | kw
    return power_plan(**args)


def test_reproduces_the_315_trades_that_t134_published():
    assert required_n(SD_T134, EFFECT_T134) == 315


def test_detectable_effect_is_the_inverse_of_the_sample_size():
    n = required_n(0.5, 0.1)
    assert min_detectable(0.5, n) <= 0.1 < min_detectable(0.5, n - 1)


@pytest.mark.parametrize("kw", [{"sd": 0.0}, {"effect": 0.0}, {"effect": -0.1}])
def test_needs_something_to_detect(kw):
    with pytest.raises(ValueError):
        required_n(kw.get("sd", 0.3), kw.get("effect", 0.1))


def test_bad_probabilities_are_refused():
    with pytest.raises(ValueError):
        required_n(0.3, 0.1, alpha=0.0)
    with pytest.raises(ValueError):
        required_n(0.3, 0.1, power=1.0)


def test_weeks_never_drop_below_the_four_of_criterion_7():
    assert plan(trades_per_week=10_000.0)["weeks"] == MIN_WEEKS
    assert plan(trades_per_week=20.0)["weeks"] == 16      # 315 / 20 → 16 semanas


def test_without_trades_there_is_no_ab():
    with pytest.raises(ValueError, match="sin operaciones"):
        plan(trades_per_week=0.0)


def test_fingerprint_covers_the_plan():
    p = plan()
    assert p["fingerprint"] == fingerprint(p)
    assert plan(effect=0.06)["fingerprint"] != p["fingerprint"]


def test_inputs_come_from_the_report_or_fail_loudly():
    rep = {"power_inputs": {"M2": {"sd_paired": {"M0": 0.4, "M1": None}}}}
    assert inputs_from_report(rep, "M2", "M0") == 0.4
    with pytest.raises(LookupError, match="insumos"):
        inputs_from_report(rep, "M9", "M0")
    with pytest.raises(LookupError, match="varianza"):
        inputs_from_report(rep, "M2", "M1")


def test_a_confirmed_plan_cannot_be_changed_afterwards(tmp_path):
    f = tmp_path / "sub" / "plan.json"
    p = plan()
    assert write_plan(p, f) == f
    assert json.loads(f.read_text(encoding="utf-8"))["required_n"] == 315
    assert write_plan(p, f) == f                          # el mismo plan: nada que hacer
    with pytest.raises(FileExistsError, match="versión nueva"):
        write_plan(plan(effect=0.06), f)
    assert json.loads(f.read_text(encoding="utf-8"))["fingerprint"] == p["fingerprint"]
