"""T162: pronósticos de varianza diaria, QLIKE, CRPS, PIT y ACI (sin red, datos sintéticos)."""

import math

import numpy as np
import pytest

from eim.forecast import vol_eval as ve
from eim.forecast import vol_models as vm
from eim.forecast.base_engine import BaseParams

DAY = vm.DAY_MS


def _minutes(days: int, sigma_day: np.ndarray, seed: int = 0):
    rng = np.random.default_rng(seed)
    t = np.arange(days * 1440, dtype=np.int64) * 60_000
    s = np.repeat(sigma_day / math.sqrt(1440), 1440)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 1, len(t)) * s))
    return t, c


def test_daily_series_rv_returns_and_coverage():
    t, c = _minutes(30, np.full(30, 0.02))
    ds = vm.daily_series(t, c)
    assert len(ds["day"]) == 30 and ds["ok"].all()
    assert np.nanmean(ds["rv"]) == pytest.approx(0.02 ** 2, rel=0.15)
    assert math.isnan(ds["ret"][0])
    last = c[1439::1440]
    assert ds["ret"][1] == pytest.approx(math.log(last[1] / last[0]))
    keep = np.ones(len(t), bool)
    keep[2 * 1440: 2 * 1440 + 300] = False           # un día con 79 % de velas
    ds2 = vm.daily_series(t[keep], c[keep])
    assert not ds2["ok"][2] and math.isnan(ds2["rv"][2])


def test_log_har_does_not_look_ahead_and_tracks_persistent_vol():
    rng = np.random.default_rng(1)
    lv = np.zeros(900)
    for i in range(1, 900):
        lv[i] = 0.95 * lv[i - 1] + rng.normal(0, 0.2)
    rv = 0.0004 * np.exp(lv)
    f = vm.m1_log_har(rv)
    assert np.isnan(f[:250]).all() and np.isfinite(f[300:]).all()
    tampered = rv.copy()
    tampered[600:] *= 50
    g = vm.m1_log_har(tampered)
    assert np.allclose(f[:601], g[:601], equal_nan=True)    # el día 600 no ve su propia RV
    ok = np.isfinite(f)
    assert np.corrcoef(np.log(f[ok]), np.log(rv[ok]))[0, 1] > 0.7


def test_fixed_garch_matches_the_closed_form_and_ignores_the_future():
    rng = np.random.default_rng(2)
    n = 24 * 120
    ht = np.arange(n + 1, dtype=np.int64) * vm.HOUR_MS
    hc = 100 * np.exp(np.cumsum(np.r_[0, rng.normal(0, 0.005, n)]))
    days = np.array([70, 90])
    p = BaseParams()
    f = vm.m0_fixed_garch(ht, hc, days, p)
    lr = np.diff(np.log(hc))
    r = lr[70 * 24 - 1 - p.lookback:70 * 24 - 1]   # la vela de las 00:00 aún no cerró
    var = float(np.var(r[:50]))
    for x in r:
        var = p.ewma_lambda * var + (1 - p.ewma_lambda) * x * x
    v = float(np.var(r))
    phi = p.garch_alpha + p.garch_beta
    want = sum(v + phi ** k * (var - v) for k in range(24))
    assert f[0] == pytest.approx(want)
    hc2 = hc.copy()
    hc2[70 * 24:] *= 3
    assert vm.m0_fixed_garch(ht, hc2, days[:1], p)[0] == pytest.approx(f[0])


def test_qlike_crps_and_pit():
    assert ve.qlike(np.array([2.0]), np.array([2.0]))[0] == pytest.approx(0.0)
    assert ve.qlike(np.array([1.0]), np.array([2.0]))[0] > 0
    # CRPS cerrado frente a la integral numérica ∫ (F(x) − 1{x ≥ y})² dx
    from scipy.stats import norm
    y, s = 0.3, 0.8
    lo, hi = np.linspace(-10, y, 400_001), np.linspace(y, 10, 400_001)
    num = (np.trapezoid(norm.cdf(lo, scale=s) ** 2, lo)
           + np.trapezoid((norm.cdf(hi, scale=s) - 1) ** 2, hi))
    assert ve.crps_normal(np.array([y]), np.array([s * s]))[0] == pytest.approx(num, rel=1e-3)
    u = ve.pit(np.random.default_rng(3).normal(0, 2, 20_000), np.full(20_000, 4.0))
    assert max(abs(x - 0.1) for x in ve.pit_deciles(u)) < 0.01


def test_aci_repairs_a_misscaled_band():
    rng = np.random.default_rng(4)
    r = rng.standard_t(4, 4000) * 0.02
    h = np.full(4000, (0.02 ** 2) * 0.5)              # σ² subestimada a la mitad
    raw = ve.band_hits(r, h).mean()
    hits = ve.aci_hits(r, h)
    adj = np.nanmean(hits)
    assert raw < 0.75 and abs(adj - 0.80) < 0.015
    assert np.isnan(hits[:250]).all()
    assert ve.worst_window(hits, 0.80) is not None


def test_gjr_garch_runs_without_look_ahead():
    pytest.importorskip("arch")
    rng = np.random.default_rng(5)
    r = rng.normal(0, 0.03, 520)
    f = vm.m2_gjr_garch(r, first=440, refit=40)
    assert np.isnan(f[:440]).all() and np.isfinite(f[440:]).all()
    r2 = r.copy()
    r2[480:] *= 10
    g = vm.m2_gjr_garch(r2, first=440, refit=40)
    assert np.allclose(f[:481], g[:481], equal_nan=True)
