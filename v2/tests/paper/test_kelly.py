"""T136 (5): Kelly fraccionado sobre el límite inferior del IC de E[R] (E10).

La prueba que pide la aceptación de la ficha es
`test_zero_whenever_the_lower_bound_is_not_positive`: sin ventaja demostrada, tamaño 0.
"""

from __future__ import annotations

import math

import pytest

from eim.paper import kelly
from eim.paper.kelly import Edge, KellyParams


def test_edge_of_a_sample():
    e = Edge.of([1.0, -1.0, 2.0, -1.0])
    assert e.n == 4
    assert e.mean_r == pytest.approx(0.25)
    assert e.m2_r == pytest.approx((1 + 1 + 4 + 1) / 4)
    assert e.se_r > 0


def test_edge_of_nothing_is_harmless():
    e = Edge.of([])
    assert e.n == 0
    assert kelly.fraction(e, KellyParams()) == 0.0
    assert kelly.risk_pct(e, KellyParams(), 0.01) == 0.0


@pytest.mark.parametrize("mean_r", [-0.154, -0.1045, -0.001, 0.0, 0.004])
def test_zero_whenever_the_lower_bound_is_not_positive(mean_r):
    """Aceptación de T136: con el límite inferior ≤ 0, el tamaño es 0. Sin excepciones.

    El 0,004 de la lista es el caso que justifica E10: media POSITIVA y, con su error, sin
    evidencia. Kelly sobre la media habría dado tamaño; sobre el límite inferior da 0.
    """
    k = KellyParams()
    e = Edge(n=1000, mean_r=mean_r, se_r=0.011, m2_r=0.9)
    assert kelly.lower_bound(e, k.z) <= 0
    assert kelly.fraction(e, k) == 0.0
    assert kelly.risk_pct(e, k, 0.02) == 0.0


def test_the_ladder_as_measured_gets_no_size():
    """Las cifras reales del banco (T131/T134): la escalera y la mejor variante dan 0."""
    k = KellyParams()
    for mean_r, se_r in ((-0.15382, 0.0085), (-0.10450, 0.0080)):
        assert kelly.risk_pct(Edge(n=29_828, mean_r=mean_r, se_r=se_r, m2_r=0.95), k, 0.02) == 0.0


def test_small_sample_gets_no_size_even_with_a_great_mean():
    k = KellyParams(n_min=30)
    e = Edge(n=5, mean_r=1.5, se_r=0.01, m2_r=2.5)
    assert kelly.lower_bound(e, k.z) > 0
    assert kelly.fraction(e, k) == 0.0


def test_a_demonstrated_edge_gets_a_fraction_and_never_more_than_the_profile():
    k = KellyParams(frac=0.25, z=1.96, n_min=30)
    e = Edge(n=500, mean_r=0.30, se_r=0.02, m2_r=1.2)
    lo = kelly.lower_bound(e, k.z)
    assert lo == pytest.approx(0.30 - 1.96 * 0.02)
    assert kelly.fraction(e, k) == pytest.approx(k.frac * lo / e.m2_r)
    assert kelly.risk_pct(e, k, 0.005) == pytest.approx(0.005)      # el perfil manda si es menor
    assert kelly.risk_pct(e, k, 0.50) == pytest.approx(kelly.fraction(e, k))


def test_fraction_never_exceeds_the_fractional_cap():
    k = KellyParams(frac=0.25)
    e = Edge(n=500, mean_r=10.0, se_r=0.01, m2_r=0.001)   # ventaja absurda a propósito
    assert kelly.fraction(e, k) == pytest.approx(0.25)


def test_degenerate_numbers_do_not_produce_size():
    k = KellyParams()
    assert kelly.fraction(Edge(n=500, mean_r=1.0, se_r=0.0, m2_r=0.0), k) == 0.0
    assert kelly.fraction(Edge(n=500, mean_r=math.nan, se_r=0.1, m2_r=1.0), k) == 0.0
    assert kelly.lower_bound(Edge(n=500, mean_r=math.inf, se_r=0.1, m2_r=1.0), 1.96) == 0.0
