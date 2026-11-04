"""T134 — el nulo por series sustitutas del criterio 6.

Lo que tiene que cumplir: conservar la distribución de retornos, destruir la dependencia serial,
dar caminos coherentes (grueso agregado del fino) y, sobre ellos, un arrastre con E[R] bruto ≈ 0.
Esa última es la que demuestra que el nulo está bien puesto: si las sustitutas dieran bruto
distinto de 0, el criterio volvería a medir una propiedad del mercado en vez de un defecto.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.paper.exits import surrogate
from eim.paper.exits.rules import Chandelier
from eim.paper.exits.trail import simulate_trail
from tests.paper.exits.helpers import SPEC, ZERO, coherent_path
from tests.paper.helpers import T0, idea

QTY = 0.01


@pytest.fixture(scope="module")
def real():
    """Una serie con dependencia serial de verdad: momento fuerte dentro de cada tramo."""
    rng = np.random.default_rng(3)
    n = 300 * 15
    base = rng.normal(0.0, 0.0004, n)
    trend = np.repeat(rng.normal(0.0, 0.0010, n // 60 + 1), 60)[:n]   # rachas de una hora
    r = base + trend
    c = 70_000.0 * np.exp(np.cumsum(r))
    return c


def test_the_surrogate_keeps_the_returns_and_only_changes_their_order(real):
    r = surrogate.log_returns(real)
    s = surrogate.shuffled(r, np.random.default_rng(1))
    assert len(s) == len(r)
    assert np.allclose(np.sort(s), np.sort(r))          # exactamente los mismos valores
    assert not np.allclose(s, r)                        # en otro orden
    assert float(s.mean()) == pytest.approx(float(r.mean()))
    assert float(s.std()) == pytest.approx(float(r.std()))


def test_shuffling_destroys_the_serial_dependence(real):
    r = surrogate.log_returns(real)
    s = surrogate.shuffled(r, np.random.default_rng(1))

    def ac1(x):
        return float(np.corrcoef(x[:-1], x[1:])[0, 1])

    assert abs(ac1(r)) > 0.2, "la serie de prueba tiene que tener dependencia"
    assert abs(ac1(s)) < 0.05


def test_blocks_keep_the_dependence_inside_them(real):
    r = surrogate.log_returns(real)
    s = surrogate.shuffled(r, np.random.default_rng(1), block=60)

    def ac1(x):
        return float(np.corrcoef(x[:-1], x[1:])[0, 1])

    assert abs(ac1(s)) > abs(ac1(surrogate.shuffled(r, np.random.default_rng(1), block=1)))


def test_the_rebuilt_coarse_path_is_aggregated_from_the_fine_one(real):
    r = surrogate.log_returns(real)
    coarse, fine = surrogate.rebuild(r, 70_000.0, T0, bars=100)
    assert len(coarse.t) == 100 and len(fine.t) == 1500
    for j in range(100):
        a, b = j * 15, (j + 1) * 15
        assert coarse.h[j] == pytest.approx(float(np.max(fine.h[a:b])))
        assert coarse.l[j] == pytest.approx(float(np.min(fine.l[a:b])))
        assert coarse.o[j] == pytest.approx(float(fine.o[a]))
        assert coarse.c[j] == pytest.approx(float(fine.c[b - 1]))


def test_rebuilding_with_too_few_returns_gives_nothing():
    coarse, fine = surrogate.rebuild(np.array([0.001, 0.002]), 100.0, T0, bars=10)
    assert len(coarse.t) == 0 and len(fine.t) == 0
    assert len(surrogate.rebuild(np.ones(100) * 0.001, 0.0, T0, bars=5)[0].t) == 0


def test_a_trail_on_the_surrogates_has_zero_gross_expectancy(real):
    """La prueba que justifica el nulo: sobre las sustitutas, el arrastre no tiene esperanza."""
    rs = []
    for s in range(60):
        rng = np.random.default_rng(100 + s)
        coarse, fine = surrogate.surrogate_of(real, rng, bars=250, px0=70_000.0, t0=T0)
        px = float(coarse.c[1])
        side = 1 if s % 2 == 0 else -1
        i = idea(side=side, entry=px, sl=px - side * px * 0.01, tp=px + side * px * 0.02,
                 t=int(coarse.t[1]) + coarse.step)
        rule = Chandelier(2.5, np.full(len(coarse.t), px * 0.004))
        o = simulate_trail(i, coarse, ZERO, rule, QTY, spec=SPEC, fine=fine)
        if o.r is not None:
            rs.append(o.r)
    a = np.array(rs, dtype=float)
    assert len(a) > 40
    half = 1.96 * float(a.std(ddof=1)) / np.sqrt(len(a))
    assert abs(float(a.mean())) <= half, f"bruto {a.mean():+.4f} fuera de ±{half:.4f}"


def test_the_p_value_is_one_sided_with_the_plus_one_correction():
    null = [0.0] * 19
    assert surrogate.one_sided_p(1.0, null) == pytest.approx(1 / 20)      # nada lo supera
    assert surrogate.one_sided_p(-1.0, null) == pytest.approx(20 / 20)    # todo lo supera
    assert np.isnan(surrogate.one_sided_p(0.5, []))


def test_the_verdict_rejects_only_what_stands_out_from_the_null():
    null = list(np.random.default_rng(5).normal(0.0, 0.01, 40))
    ok = surrogate.verdict(0.005, null, 0.05)
    assert ok["ok"] is True and ok["p_one_sided"] > 0.05
    bad = surrogate.verdict(0.5, null, 0.05)
    assert bad["ok"] is False and bad["p_one_sided"] <= 0.05
    assert bad["surrogates"] == 40 and bad["null_p95"] is not None
    none = surrogate.verdict(0.1, [], 0.05)
    assert none["ok"] is None and "sin sustitutas" in none["reason"]


def test_the_null_does_not_depend_on_the_fixture_being_a_random_walk():
    """Con una serie que SÍ tiene momento, el nulo se centra en 0 igual: eso es el punto."""
    rng = np.random.default_rng(9)
    coarse, fine = coherent_path(200, seed=11)
    r = surrogate.log_returns(fine.c)
    s1, _ = surrogate.surrogate_of(fine.c, rng, bars=150, px0=70_000.0, t0=T0)
    assert len(s1.t) == 150
    assert float(np.mean(surrogate.shuffled(r, rng))) == pytest.approx(float(np.mean(r)))
