"""Mirada final, e-procesos, temas y conexión al libro de la cantera (T170). Sintético."""

from __future__ import annotations

import numpy as np

from eim.nursery import calibrate, evalue, themes
from eim.nursery.ladder import BAJA, PRIMER, evaluate
from eim.nursery.ladder_final import make_first_team, n_effective
from eim.nursery.ladder_io import closed_spans
from eim.nursery.ladder_stats import AccountData, Closed
from tests.nursery.test_ladder import ALTA, END, PR, _account, _member, _rules

REGIMES = ("trend_up", "trend_down", "range")


def _with_regime(d):
    a = _account(d)
    return AccountData(tuple(Closed(c.t, c.fill_t, c.exit_t, c.d, c.pnl_usd, 0.1, c.d,
                                    REGIMES[i % 3]) for i, c in enumerate(a.closed)), a.fills)


def test_first_team_needs_the_strict_gate():
    rng = np.random.default_rng(9)
    ids = ["fuerte", *(f"nulo{i}" for i in range(6))]
    acc = {"fuerte": _with_regime(rng.normal(0.6, 1.0, 400))}
    acc |= {i: _with_regime(calibrate.null_d(rng, (200,))) for i in ids[1:]}
    rules = _rules(ids)
    rules = rules.model_copy(update={"first_team": rules.first_team.model_copy(
        update={"stepm_reps": 1000})})
    m = len(ids) + 7
    st = evaluate([_member(i) for i in ids], acc, rules, ALTA, END, m, 10_000.0,
                  first_team=make_first_team(rules, ALTA, m, 10_000.0))
    assert st["fuerte"].stage == PRIMER
    assert all(c["ok"] for c in st["fuerte"].criteria if c["id"] in (
        "stepm", "dsr", "regimenes", "persistencia", "v1", "v4", "v5", "v6"))
    assert all(st[i].stage == BAJA for i in ids[1:])


def test_ebh_and_mixture_basics():
    assert evalue.ebh([400, 1, 50, 100], 4, 0.1) == {0, 2, 3}    # 400 ≥ 40, 100 ≥ 20, 50 ≥ 13,3
    assert evalue.ebh([400, 1, 15, 12], 4, 0.1) == {0}            # 15 < 20 y 12 < 13,3
    assert evalue.ebh([25, 25, 0], 3, 0.1) == {0, 1}              # 25 ≥ 3/(0,1·2) = 15
    assert evalue.ebh([], 5, 0.1) == set()
    y = evalue.scaled([0.0] * 10, 3.0)
    assert np.allclose(evalue.mixture(y, [0.5]), 1.0)
    rng = np.random.default_rng(0)
    path = evalue.mixture(evalue.scaled(calibrate.null_d(rng, (4000, 100)), 3.0),
                          PR.ladder.primary.lambdas)
    assert path[:, -1].mean() < 1.1                               # supermartingala bajo H0


def test_n_effective_groups_correlated_prospects():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, (200, 1))
    mat = np.column_stack([x[:, 0], x[:, 0] + rng.normal(0, 0.05, 200),
                           rng.normal(0, 1, 200), np.zeros(200)])
    assert n_effective(mat, 0.7) == 3


def test_shrinkage_pulls_toward_the_theme():
    rng = np.random.default_rng(2)
    d = {"a": rng.normal(0.5, 1, 40), "b": rng.normal(0.0, 1, 400),
         "c": rng.normal(0.0, 1, 400)}
    th = {"a": "tendencia", "b": "tendencia", "c": "tendencia"}
    s = themes.shrink(d, th, 3.0)
    assert abs(s["a"]["shrunk"]) <= abs(s["a"]["raw"])
    tests = themes.theme_tests(d, th, 3.0, 0.10)
    assert set(tests) == {"tendencia"} and "p_holm" in tests["tendencia"]
    nv = themes.native_vs_generic({"x": list(rng.normal(0.4, 1, 300))},
                                  {"x": list(rng.normal(0.0, 1, 300))}, 0.10)
    assert nv["x"]["native_better"] is True


def test_closed_spans_from_cost_gate_events():
    ev = [{"t": 10, "kind": "puerta_costo", "timeframe": "15m", "after": "cerrado"},
          {"t": 50, "kind": "puerta_costo", "timeframe": "15m", "after": "abierto"},
          {"t": 70, "kind": "puerta_costo", "timeframe": "15m", "after": "cerrado"},
          {"t": 5, "kind": "puerta_costo", "timeframe": "1h", "after": "abierto"}]
    assert closed_spans(ev, 100) == {"15m": [(10, 50), (70, 100)]}


def test_drawdown_cap_grows_with_the_number_of_trades():
    a = calibrate.dd_cap(100, 0.25, 1.3, 0.01, 0.05, 4000, 1)
    b = calibrate.dd_cap(1000, 0.25, 1.3, 0.01, 0.05, 4000, 1)
    assert 0 < a < b < 30
