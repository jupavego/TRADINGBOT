"""T100: volatilidad implícita. Hull, §15.11: c=1,875 con S=21, K=20, r=10 %, T=0,25 →
σ implícita ≈ 23,5 %."""

import pytest

from eim.options import black_scholes as bs
from eim.options.implied_vol import NoImpliedVol, implied_vol, implied_vol_black76


def test_hull_implied_vol():
    assert implied_vol(1.875, 21, 20, 0.25, 0.10) == pytest.approx(0.235, abs=5e-4)


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("k", [60.0, 95.0, 100.0, 140.0])
@pytest.mark.parametrize("sigma", [0.05, 0.3, 1.2])
def test_round_trip(kind, k, sigma):
    px = bs.price(100, k, 0.5, 0.03, sigma, kind)
    if px - bs.bounds(100, k, 0.5, 0.03, kind)[0] < 1e-10:
        pytest.skip("sin valor temporal medible")
    assert implied_vol(px, 100, k, 0.5, 0.03, kind) == pytest.approx(sigma, rel=1e-6)


def test_black76_round_trip():
    px = bs.black76(19, 19, 0.75, 0.10, 0.28)
    assert implied_vol_black76(px, 19, 19, 0.75, 0.10) == pytest.approx(0.28, abs=1e-9)


def test_out_of_bounds_prices_have_no_implied_vol():
    with pytest.raises(NoImpliedVol, match="cota inferior"):
        implied_vol(1.0, 100, 90, 0.5, 0.0)            # por debajo del intrínseco (10)
    with pytest.raises(NoImpliedVol, match="cota superior"):
        implied_vol(100.0, 100, 90, 0.5, 0.0)
    with pytest.raises(NoImpliedVol, match="vencida"):
        implied_vol(5.0, 100, 90, 0.0, 0.0)
