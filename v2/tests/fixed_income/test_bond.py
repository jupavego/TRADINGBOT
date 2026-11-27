"""T100: bono de cupón fijo contra valores publicados.

Referencias:
- Hull, *Options, Futures, and Other Derivatives*, §4.8–4.9 (tabla 4.6): bono a 3 años,
  cupón 10 % semestral, rendimiento 12 % continuo → precio 94,213, duración 2,653 años y
  convexidad 7,570.
- Fabozzi, *Bond Markets, Analysis, and Strategies* (cap. 4): bono a 20 años, cupón 9 %
  semestral, rendimiento 6 % → precio 134,6722 y convexidad 164,106 (de rendimiento
  semestral equivalente).
"""

import math

import pytest

from eim.fixed_income import bond as b


def test_hull_price_duration_convexity_continuous():
    f = b.cashflows(0.10, 3, 2)
    assert f == ((0.5, 1.0, 1.5, 2.0, 2.5, 3.0), (5.0, 5.0, 5.0, 5.0, 5.0, 105.0))
    assert b.price(f, 0.12, "continuous") == pytest.approx(94.213, abs=5e-4)
    assert b.macaulay_duration(f, 0.12, "continuous") == pytest.approx(2.653, abs=5e-4)
    assert b.modified_duration(f, 0.12, "continuous") == b.macaulay_duration(
        f, 0.12, "continuous")
    assert b.convexity(f, 0.12, "continuous") == pytest.approx(7.570, abs=5e-4)


def test_fabozzi_price_and_convexity_semiannual():
    f = b.cashflows(0.09, 20, 2)
    assert b.price(f, 0.06) == pytest.approx(134.6722, abs=5e-5)
    assert b.convexity(f, 0.06) == pytest.approx(164.106, abs=5e-4)


def test_par_bond_prices_at_100_and_yield_round_trip():
    f = b.cashflows(0.08, 10, 2)
    assert b.price(f, 0.08) == pytest.approx(100.0, abs=1e-9)
    for y in (0.0, 0.03, 0.08, 0.15):
        assert b.yield_from_price(f, b.price(f, y)) == pytest.approx(y, abs=1e-10)


def test_derivatives_match_finite_differences():
    f = b.cashflows(0.05, 7.3, 2)
    y, h = 0.047, 1e-5
    p0, up, dn = b.price(f, y), b.price(f, y + h), b.price(f, y - h)
    assert b.modified_duration(f, y) == pytest.approx(-(up - dn) / (2 * h) / p0, rel=1e-6)
    assert b.convexity(f, y) == pytest.approx((up - 2 * p0 + dn) / (h * h) / p0, rel=1e-4)
    assert b.dv01(f, y) == pytest.approx((dn - up) / 2 * (1e-4 / h), rel=1e-5)


def test_second_order_approximation_beats_duration_alone():
    f = b.cashflows(0.04, 30, 2)
    approx, exact = b.price_change(f, 0.05, 0.01)
    duration_only = -b.modified_duration(f, 0.05) * 0.01
    assert abs(approx - exact) < abs(duration_only - exact) / 5


def test_odd_first_period_and_accrued():
    f = b.cashflows(0.06, 2.25, 2)
    assert f[0] == (0.25, 0.75, 1.25, 1.75, 2.25)
    assert b.accrued(0.06, 2.25, 2) == pytest.approx(1.5)        # medio periodo de 3 €
    assert b.accrued(0.06, 2.0, 2) == pytest.approx(0.0)


def test_curve_pricing_equals_yield_pricing_on_a_flat_curve():
    f = b.cashflows(0.07, 5, 2)
    y = 0.06
    assert b.price_on_curve(f, lambda _t: y) == pytest.approx(b.price(f, y, "continuous"))
    assert b.par_yield(lambda _t: math.log(1.03) * 2, 5) == pytest.approx(0.06, abs=1e-12)


def test_invalid_inputs():
    with pytest.raises(ValueError):
        b.cashflows(0.05, 0, 2)
    with pytest.raises(ValueError):
        b.yield_from_price(b.cashflows(0.05, 5), -1)
    with pytest.raises(ValueError):
        b.price(b.cashflows(0.05, 5), 0.05, comp="simple")
