"""T100: Black–Scholes generalizado y griegas contra valores publicados.

- Hull, ejemplo 15.6: S=42, K=40, r=10 %, σ=20 %, T=0,5 → call 4,76 y put 0,81.
- Hull, ejemplos 19.1–19.8: S=49, K=50, r=5 %, σ=20 %, T=20/52 → call 2,40; delta 0,522;
  gamma 0,066; vega 12,1; theta −4,31 por año; rho 8,91.
- Haug, *The Complete Guide to Option Pricing Formulas*: BSM generalizado S=60, K=65,
  T=0,25, r=b=8 %, σ=30 % → call 2,1334; Merton con dividendo S=100, K=95, T=0,5, r=10 %,
  q=5 %, σ=20 % → put 2,4648; Black-76 F=K=19, T=0,75, r=10 %, σ=28 % → call = put = 1,7011;
  Garman–Kohlhagen S=1,56, K=1,60, T=0,5, r=6 %, r_f=8 %, σ=12 % → call 0,0291.
"""

import pytest

from eim.options import black_scholes as bs


def test_hull_prices():
    assert bs.price(42, 40, 0.5, 0.10, 0.20, "call") == pytest.approx(4.76, abs=5e-3)
    assert bs.price(42, 40, 0.5, 0.10, 0.20, "put") == pytest.approx(0.81, abs=5e-3)


def test_hull_greeks():
    g = bs.greeks(49, 50, 20 / 52, 0.05, 0.20)
    assert g.price == pytest.approx(2.40, abs=5e-3)
    assert g.delta == pytest.approx(0.522, abs=5e-4)
    assert g.gamma == pytest.approx(0.066, abs=5e-4)
    assert g.vega == pytest.approx(12.1, abs=5e-2)
    assert g.theta == pytest.approx(-4.31, abs=5e-3)
    assert g.rho == pytest.approx(8.91, abs=5e-3)


def test_haug_generalized_merton_black76_and_fx():
    assert bs.price(60, 65, 0.25, 0.08, 0.30, "call", b=0.08) == pytest.approx(2.1334, abs=5e-5)
    assert bs.price(100, 95, 0.5, 0.10, 0.20, "put", b=0.05) == pytest.approx(2.4648, abs=5e-5)
    for kind in ("call", "put"):
        assert bs.black76(19, 19, 0.75, 0.10, 0.28, kind) == pytest.approx(1.7011, abs=5e-5)
    assert bs.price(1.56, 1.60, 0.5, 0.06, 0.12, "call", b=-0.02) == pytest.approx(
        0.0291, abs=5e-5)


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("b", [None, 0.0, 0.02])
def test_greeks_match_finite_differences(kind, b):
    s, k, t, r, v = 100.0, 105.0, 0.7, 0.03, 0.25
    g = bs.greeks(s, k, t, r, v, kind, b=b)

    def p(**kw):
        a = {"s": s, "k": k, "t": t, "r": r, "sigma": v} | kw
        bb = a["r"] if b is None else b
        return bs.price(a["s"], a["k"], a["t"], a["r"], a["sigma"], kind, b=bb)

    h = 1e-4
    assert g.delta == pytest.approx((p(s=s + h) - p(s=s - h)) / (2 * h), rel=1e-6)
    assert g.gamma == pytest.approx((p(s=s + h) - 2 * p() + p(s=s - h)) / h**2, rel=1e-3)
    assert g.vega == pytest.approx((p(sigma=v + h) - p(sigma=v - h)) / (2 * h), rel=1e-6)
    assert g.theta == pytest.approx(-(p(t=t + h) - p(t=t - h)) / (2 * h), rel=1e-5)
    if b is None:   # el carry se mueve con r: rho es la derivada con b = r
        assert g.rho == pytest.approx((p(r=r + h) - p(r=r - h)) / (2 * h), rel=1e-5)


def test_black76_rho_is_minus_t_times_price():
    g = bs.greeks(19, 19, 0.75, 0.10, 0.28, "call", b=0.0)
    assert g.rho == pytest.approx(-0.75 * g.price)


def test_put_call_parity_and_bounds():
    c = bs.price(100, 90, 1.0, 0.04, 0.3, "call", b=0.01)
    p = bs.price(100, 90, 1.0, 0.04, 0.3, "put", b=0.01)
    assert bs.parity_gap(c, p, 100, 90, 1.0, 0.04, b=0.01) == pytest.approx(0, abs=1e-12)
    lo, hi = bs.bounds(100, 90, 1.0, 0.04, "call")
    assert lo < c < hi


def test_invalid_inputs():
    with pytest.raises(ValueError):
        bs.price(100, 100, 0, 0.01, 0.2)
    with pytest.raises(ValueError):
        bs.price(100, 100, 1, 0.01, 0.2, kind="straddle")
