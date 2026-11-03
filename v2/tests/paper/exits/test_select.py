"""T131 — el objetivo de selección pre-registrado (E2): qué se maximiza y con qué restricciones.

«Lo que se optimiza es lo que se obtiene» (Sutton y Barto §17.4): si el banco eligiera por E[R] sin
mirar la cola, adoptaría la variante que gana de media y arruina en el peor mes. Y si eligiera el
pico de la rejilla, adoptaría ruido.

La meseta se mide sobre **la mejora frente a la base**, no sobre el E[R] absoluto (v2 del
pre-registro). Importa de verdad: en el mercado medido todas las variantes tienen E[R] < 0 porque
la entrada no tiene ventaja, así que con el nivel absoluto no se elegiría nunca nada.
"""

from __future__ import annotations

from eim.paper.exits import select as sel

BASE = {"n": 100, "expectancy_r": 0.0, "cvar95_r": -1.0, "max_dd_r": 8.0}
LOSING_BASE = {"n": 100, "expectancy_r": -0.159, "cvar95_r": -1.35, "max_dd_r": 4755.0}


def m(exp: float, cvar: float = -0.9, dd: float = 7.0, n: int = 100) -> dict:
    return {"n": n, "expectancy_r": exp, "cvar95_r": cvar, "max_dd_r": dd}


def test_a_variant_that_improves_the_mean_by_worsening_the_tail_is_not_feasible():
    worse_tail = sel.score_of("v", m(0.20, cvar=-1.4), BASE)
    assert worse_tail.feasible is False and "CVaR" in worse_tail.why
    worse_dd = sel.score_of("v", m(0.20, dd=9.0), BASE)
    assert worse_dd.feasible is False and "DD" in worse_dd.why
    ok = sel.score_of("v", m(0.10), BASE)
    assert ok.feasible is True and ok.expectancy_r == 0.10 and ok.improvement == 0.10


def test_a_small_sample_is_not_feasible_and_says_so():
    s = sel.score_of("v", m(0.5, n=3), BASE, min_trades=30)
    assert s.feasible is False and "muestra insuficiente" in s.why
    assert s.to_json()["variant"] == "v"


def test_the_centre_of_the_plateau_beats_an_isolated_peak():
    """`k3` gana aunque `k9` tenga mejor E[R]: el pico se queda solo y la meseta no."""
    scores = {k: sel.score_of(k, m(v), BASE) for k, v in
              {"k2": 0.09, "k3": 0.10, "k4": 0.095, "k9": 0.14}.items()}
    nb = {"k2": ["k3"], "k3": ["k2", "k4"], "k4": ["k3", "k9"], "k9": ["k4"]}
    got = sel.choose(scores, nb)
    assert got["winner"] == "k3"
    assert "centro de la meseta" in got["reason"]
    assert got["neighbourhood_min"] == 0.09


def test_a_losing_market_can_still_choose_the_exit_that_loses_less():
    """El caso real: todas las variantes pierden. La mejora frente a la base sí ordena."""
    scores = {k: sel.score_of(k, m(v, cvar=-1.35, dd=4700.0), LOSING_BASE) for k, v in
              {"a": -0.152, "b": -0.150, "c": -0.151, "d": -0.175}.items()}
    nb = {"a": ["b"], "b": ["a", "c"], "c": ["b", "d"], "d": ["c"]}
    got = sel.choose(scores, nb)
    assert got["winner"] == "b"
    assert got["improvement"] > 0 and got["expectancy_r"] < 0
    assert all(s.expectancy_r < 0 for s in scores.values())
    assert sel.plateau_ok(scores, nb)["d"] is False      # la que empeora a la base no es meseta


def test_a_variant_that_does_not_beat_the_base_never_forms_a_plateau():
    scores = {k: sel.score_of(k, m(v, cvar=-1.35, dd=4700.0), LOSING_BASE) for k, v in
              {"a": -0.170, "b": -0.165}.items()}
    assert sel.choose(scores, {"a": ["b"], "b": ["a"]})["winner"] is None


def test_an_infeasible_peak_cannot_win_even_if_it_forms_a_plateau():
    scores = {"a": sel.score_of("a", m(0.3, cvar=-2.0), BASE),
              "b": sel.score_of("b", m(0.29, cvar=-2.0), BASE),
              "c": sel.score_of("c", m(0.05), BASE),
              "d": sel.score_of("d", m(0.049), BASE)}
    got = sel.choose(scores, {"a": ["b"], "b": ["a"], "c": ["d"], "d": ["c"]})
    assert got["winner"] in {"c", "d"}
    assert set(got["feasible"]) == {"c", "d"}


def test_without_a_plateau_nothing_is_chosen_and_el_pico_queda_a_la_vista():
    """Una variante mala pegada a una buena cumple «mis vecinos conservan mi mejora» y NO sirve:
    sin la condición de ser competitiva, la regla elegiría justo la peor de la rejilla."""
    scores = {"a": sel.score_of("a", m(0.20), BASE), "b": sel.score_of("b", m(0.01), BASE)}
    nb = {"a": ["b"], "b": ["a"]}
    assert sel.plateau_ok(scores, nb)["b"] is True     # la trampa: su vecino es mejor
    got = sel.choose(scores, nb)
    assert got["winner"] is None                       # pero no llega al 70 % de la mejor mejora
    assert got["best_unconstrained"] == "a"            # se informa, pero no se adopta
    assert "ninguna variante factible" in got["reason"]


def test_the_neighbours_of_a_one_parameter_grid_are_the_adjacent_steps():
    nb = sel.neighbours_of([0.075, 0.1, 0.25, 0.5, 1.0])
    assert nb["0.075"] == ["0.1"]
    assert nb["0.25"] == ["0.1", "0.5"]
    assert nb["1"] == ["0.5"]


def test_a_variant_without_declared_neighbours_is_not_a_plateau():
    scores = {"solo": sel.score_of("solo", m(0.3), BASE)}
    assert sel.plateau_ok(scores, {})["solo"] is False
    assert sel.choose(scores, {})["winner"] is None
