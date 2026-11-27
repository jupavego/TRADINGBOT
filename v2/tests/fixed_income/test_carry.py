"""T100: carry y roll-down con la curva quieta (identidades exactas)."""

import math

import pytest
from scipy.integrate import quad

from eim.fixed_income import carry as k
from eim.fixed_income.bond import cashflows, price_on_curve
from eim.fixed_income.curve import forward_rate, linear


def test_flat_curve_has_no_rolldown():
    cr = k.zero_coupon(lambda _t: 0.04, 10, 0.25, funding_rate=0.03)
    assert cr.rolldown == pytest.approx(0.0, abs=1e-15)
    assert cr.carry == pytest.approx(0.01)
    assert cr.excess == pytest.approx(0.0025)
    assert cr.breakeven_bp(9.75) == pytest.approx(0.0025 / 9.75 * 1e4)


def test_zero_coupon_total_is_the_forward_integral_and_the_log_return():
    zero = linear([0.25, 2, 5, 10, 30], [0.040, 0.042, 0.045, 0.048, 0.052])
    cr = k.zero_coupon(zero, 10, 0.5)
    p0 = math.exp(-zero(10) * 10)
    p_h = math.exp(-zero(9.5) * 9.5)
    assert cr.total == pytest.approx(math.log(p_h / p0), abs=1e-14)
    integral, _ = quad(lambda s: forward_rate(zero, s, s + 1e-6), 9.5, 10, points=[10])
    assert cr.total == pytest.approx(integral, abs=1e-6)
    assert cr.rolldown > 0                       # curva con pendiente positiva: rueda a favor


def test_coupon_bond_on_flat_curve_is_pure_carry():
    y = 0.05
    f = cashflows(0.05, 5, 2)
    cr = k.coupon_bond(lambda _t: y, f, 0.5)
    assert cr.rolldown == pytest.approx(0.0, abs=1e-9)
    assert cr.carry == pytest.approx(math.exp(y * 0.5) - 1, abs=1e-9)


def test_coupon_bond_total_matches_repricing():
    zero = linear([0.5, 2, 5, 10], [0.03, 0.035, 0.04, 0.045])
    f = cashflows(0.04, 10, 2)
    cr = k.coupon_bond(zero, f, 1.0, funding_rate=0.03)
    p0 = price_on_curve(f, zero)
    later = [(t - 1, a) for t, a in zip(*f, strict=True) if t > 1]
    p1 = price_on_curve((tuple(t for t, _ in later), tuple(a for _, a in later)), zero)
    assert cr.total == pytest.approx((p1 + 4.0) / p0 - 1, abs=1e-12)   # dos cupones de 2
    assert cr.funding == pytest.approx(math.exp(0.03) - 1)


def test_horizon_must_be_inside_maturity():
    with pytest.raises(ValueError):
        k.zero_coupon(lambda _t: 0.04, 1, 1)
