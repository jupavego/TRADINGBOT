"""T136 (4), E12: la comprobación del ES de Acerbi y Székely detecta un CVaR mal calibrado."""

from __future__ import annotations

import math

import numpy as np
import pytest

from eim.paper.exits import es_check as es
from eim.validation.stats import rng_for


def _days(n: int, per_day: int = 5) -> np.ndarray:
    return np.repeat(np.arange((n + per_day - 1) // per_day), per_day)[:n]


def test_var_and_es_are_positive_magnitudes_of_the_same_tail():
    rs = np.array([-3.0, -2.0, -1.0, 0.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    var, e = es.var_es(rs, level=0.8)
    assert var > 0 and e > 0
    assert e >= var                                   # la media de la cola es peor que su canto
    assert math.isnan(es.var_es(np.array([1.0]))[0])


def test_z2_is_about_zero_when_the_model_is_right():
    rng = np.random.default_rng(7)
    rs = rng.normal(0.0, 1.0, 20_000)
    var, e = es.var_es(rs)
    assert es.z2(rs, var, e) == pytest.approx(0.0, abs=0.02)


def test_z2_is_negative_when_the_real_tail_is_worse():
    rng = np.random.default_rng(11)
    mild = rng.normal(0.0, 1.0, 10_000)
    var, e = es.var_es(mild)
    harsh = rng.normal(0.0, 1.0, 10_000) * 2.5        # misma forma, cola mucho peor
    assert es.z2(harsh, var, e) < -0.5


def test_z2_is_positive_when_the_real_tail_is_milder():
    rng = np.random.default_rng(13)
    var, e = es.var_es(rng.normal(0.0, 2.5, 10_000))
    assert es.z2(rng.normal(0.0, 1.0, 10_000), var, e) > 0.2


def test_degenerate_inputs_give_nan_not_an_exception():
    assert math.isnan(es.z2(np.array([]), 1.0, 1.0))
    assert math.isnan(es.z2(np.array([1.0, -1.0]), math.nan, 1.0))
    assert math.isnan(es.z2(np.array([1.0, -1.0]), 1.0, 0.0))


def test_check_says_no_sample_instead_of_inventing_a_verdict():
    rng = rng_for(1, "t136|es|vacio")
    out = es.check(np.array([0]), np.array([0.1]), np.array([0]), np.array([0.1]), 100, rng)
    assert out["verdict"] == "sin muestra" and out["z2"] is None and out["p"] is None


def test_check_flags_an_underestimated_es():
    rng = np.random.default_rng(3)
    fit = rng.normal(0.0, 1.0, 4_000)
    test = rng.normal(0.0, 1.0, 4_000) * 2.5
    out = es.check(_days(len(fit)), fit, _days(len(test)), test, 500,
                   rng_for(1, "t136|es|corto"))
    assert out["es_underestimated"] is True
    assert out["p"] <= 0.05
    assert out["es_test_r"] < out["es_fit_r"]          # la cola real es peor (más negativa)


def test_check_does_not_cry_wolf_when_the_tail_matches():
    rng = np.random.default_rng(5)
    fit, test = rng.normal(0.0, 1.0, 4_000), rng.normal(0.0, 1.0, 4_000)
    out = es.check(_days(len(fit)), fit, _days(len(test)), test, 500,
                   rng_for(1, "t136|es|ok"))
    assert out["es_underestimated"] is False
    assert out["p"] > 0.05


def test_check_is_reproducible_with_the_same_seed():
    rng = np.random.default_rng(17)
    fit, test = rng.normal(0.0, 1.0, 2_000), rng.normal(0.0, 1.3, 2_000)
    args = (_days(len(fit)), fit, _days(len(test)), test, 300)
    a = es.check(*args, rng_for(9, "t136|es|rep"))
    b = es.check(*args, rng_for(9, "t136|es|rep"))
    assert a == b
