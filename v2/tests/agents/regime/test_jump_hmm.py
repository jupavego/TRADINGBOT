"""Modelo de saltos y HMM gaussiano (T166): series sintéticas con regímenes conocidos.

Las pruebas atacan las propiedades que la comparación pre-registrada necesita y que un error
silencioso rompería: que el DP minimice de verdad lo que dice minimizar, que la penalización haga
lo que promete, que la asignación en línea no mire al futuro y que los dos modelos recuperen un
régimen que está puesto a mano. Sin red y sin disco.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from eim.agents.regime import hmm, jump


def _two_regimes(seed: int = 166, n: int = 300) -> tuple[np.ndarray, np.ndarray]:
    """Dos tramos de 150 días: el primero con media 0 y el segundo con media +3 en dos rasgos."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 3))
    truth = np.zeros(n, dtype=int)
    truth[n // 2:] = 1
    x[n // 2:, :2] += 3.0
    return x, truth


def _objective(cost: np.ndarray, states: np.ndarray, lam: float) -> float:
    return float(cost[np.arange(len(states)), states].sum()
                 + lam * np.sum(states[1:] != states[:-1]))


def test_dp_finds_the_true_minimum_by_brute_force():
    rng = np.random.default_rng(0)
    cost = rng.normal(size=(9, 3)) ** 2
    for lam in (0.0, 0.5, 2.0, 50.0):
        best = min(itertools.product(range(3), repeat=9),
                   key=lambda s: _objective(cost, np.array(s), lam))
        got = jump.assign_dp(cost, lam)
        assert _objective(cost, got, lam) <= _objective(cost, np.array(best), lam) + 1e-12


def test_a_bigger_penalty_never_adds_jumps():
    cost = np.random.default_rng(1).normal(size=(200, 2)) ** 2
    jumps = [int(np.sum(np.diff(jump.assign_dp(cost, lam)) != 0))
             for lam in (0.0, 1.0, 10.0, 1e6)]
    assert jumps == sorted(jumps, reverse=True)
    assert jumps[-1] == 0          # con lam enorme queda un solo estado


def test_the_jump_model_recovers_a_regime_it_was_given():
    x, truth = _two_regimes()
    labels = jump.fit(x, 2, lam=10.0).labels
    agree = max(float(np.mean(labels == truth)), float(np.mean(labels != truth)))
    assert agree > 0.95
    assert int(np.sum(np.diff(labels) != 0)) <= 3


def test_the_fit_objective_does_not_grow_with_more_iterations():
    x, _ = _two_regimes(seed=7)
    objs = [jump.fit(x, 2, lam=5.0, max_iter=i).objective for i in (1, 2, 5, 20)]
    assert all(b <= a + 1e-9 for a, b in zip(objs[:-1], objs[1:], strict=True))


def test_the_filtered_assignment_ignores_the_future():
    """El estado del día `i` no cambia si se recorta la serie justo después de él."""
    x, _ = _two_regimes(seed=3)
    model = jump.fit(x[:150], 2, lam=10.0)
    full = jump.assign_filtered(x, model)
    for cut in (160, 200, 250):
        assert np.array_equal(jump.assign_filtered(x[:cut], model), full[:cut])


def test_the_filtered_assignment_tracks_a_regime_the_dp_also_finds():
    """El filtro es la versión en línea del DP: con un régimen claro, coinciden casi siempre."""
    x, truth = _two_regimes(seed=23)
    model = jump.fit(x, 2, lam=10.0)
    s = jump.assign_filtered(x, model)
    agree = max(float(np.mean(s == truth)), float(np.mean(s != truth)))
    assert agree > 0.95


def test_the_penalty_in_data_units_does_not_depend_on_the_scale_of_the_features():
    """`fit_scaled` mide el salto en unidades de los datos: multiplicar los rasgos no cambia nada.

    Es el motivo del cambio a v2 del pre-registro: con un λ absoluto, la misma rejilla significa
    cosas distintas según cuántos rasgos haya y cómo se hayan estandarizado.
    """
    x, _ = _two_regimes(seed=29)
    a = jump.assign_filtered(x, jump.fit_scaled(x, 2, 2.0))
    b = jump.assign_filtered(10.0 * x, jump.fit_scaled(10.0 * x, 2, 2.0))
    assert np.array_equal(a, b)
    assert jump.scale_for(10.0 * x, 2) == pytest.approx(100.0 * jump.scale_for(x, 2), rel=1e-9)


def test_a_bigger_c_gives_more_persistent_states():
    x, _ = _two_regimes(seed=31, n=600)
    x += np.random.default_rng(31).normal(0.0, 1.5, size=x.shape)   # ruido que invita a saltar
    jumps = [int(np.sum(np.diff(jump.assign_filtered(x, jump.fit_scaled(x, 2, c))) != 0))
             for c in (0.5, 2.0, 8.0)]
    assert jumps == sorted(jumps, reverse=True)


def test_the_dp_does_look_at_the_future_so_it_is_not_used_to_evaluate():
    """Contraste del anterior: `assign_dp` sí mira hacia delante, y por eso solo se usa al ajustar.

    Fija el motivo de que la evaluación use `assign_online`: si algún día alguien cambia el
    script y evalúa con el DP, esta prueba explica qué se rompió.
    """
    cost = np.array([[0.0, 0.4], [0.0, 0.4], [0.0, 0.4], [10.0, 0.0], [10.0, 0.0]])
    assert jump.assign_dp(cost, 5.0)[0] == 1       # arranca ya en el estado que vendra
    assert jump.assign_dp(cost[:3], 5.0)[0] == 0   # con la serie recortada, no lo sabe


def test_the_hmm_recovers_the_same_regime_and_a_persistent_transition():
    x, truth = _two_regimes(seed=11)
    model = hmm.fit(x, 2)
    s = hmm.filter_states(x, model)
    agree = max(float(np.mean(s == truth)), float(np.mean(s != truth)))
    assert agree > 0.95
    assert min(model.trans[0, 0], model.trans[1, 1]) > 0.9
    assert np.allclose(model.trans.sum(axis=1), 1.0)


def test_the_hmm_loglikelihood_does_not_fall_between_iterations():
    x, _ = _two_regimes(seed=13)
    lls = [hmm.fit(x, 2, max_iter=i, tol=0.0).loglik for i in (2, 4, 8, 16)]
    assert all(b >= a - 1e-6 for a, b in zip(lls[:-1], lls[1:], strict=True))


def test_the_hmm_filter_ignores_the_future():
    x, _ = _two_regimes(seed=17)
    model = hmm.fit(x[:150], 2)
    full = hmm.filter_states(x, model)
    for cut in (160, 220, 299):
        assert np.array_equal(hmm.filter_states(x[:cut], model), full[:cut])


def test_both_models_are_deterministic():
    x, _ = _two_regimes(seed=19)
    assert np.array_equal(jump.fit(x, 2, 10.0).labels, jump.fit(x, 2, 10.0).labels)
    assert hmm.fit(x, 2).loglik == hmm.fit(x, 2).loglik
