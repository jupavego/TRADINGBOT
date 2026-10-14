"""Pruebas del laboratorio (fuera del gate): `python -m pytest lab/esn_connectome -q`."""

from __future__ import annotations

import numpy as np

from lab.esn_connectome import features
from lab.esn_connectome.esn import ESNParams, build_reservoir, run_states, spectral_scale
from lab.esn_connectome.models import QUANTILES, fit_select, pinball


def _signed(n: int = 60) -> np.ndarray:
    r = np.random.default_rng(1)
    m = (r.random((n, n)) < 0.1) * r.integers(1, 30, (n, n)).astype(float)
    return m * np.where(r.random(n) < 0.3, -1, 1)[None, :]


def test_variants_share_density_and_topology() -> None:
    s = _signed()
    rng = np.random.default_rng(0)
    w_c = build_reservoir("connectome", s, rng)
    w_t = build_reservoir("topology", s, rng)
    w_r = build_reservoir("random", s, rng)
    assert ((w_c != 0) == (s != 0)).all()
    assert ((w_t != 0) == (s != 0)).all()
    assert (w_r != 0).sum() == (s != 0).sum()
    assert np.sign(w_c[s != 0]).tolist() == np.sign(s[s != 0]).tolist()


def test_spectral_radius() -> None:
    w = spectral_scale(build_reservoir("connectome", _signed(), np.random.default_rng(0)), 0.9)
    assert abs(np.max(np.abs(np.linalg.eigvals(w))) - 0.9) < 1e-9


def test_states_are_causal() -> None:
    w = build_reservoir("random", _signed(), np.random.default_rng(0))
    u = np.random.default_rng(2).standard_normal((300, 4))
    u2 = u.copy()
    u2[200:] += 5.0
    a = run_states(w, u, ESNParams(), np.random.default_rng(3))
    b = run_states(w, u2, ESNParams(), np.random.default_rng(3))
    assert np.allclose(a[:200], b[:200])
    assert not np.allclose(a[200:], b[200:])


def test_features_target_alignment() -> None:
    c = np.exp(np.cumsum(np.random.default_rng(4).normal(0, 0.01, 400))) * 100
    ohlcv = np.stack([c, c * 1.01, c * 0.99, c, np.ones_like(c)], axis=1)
    f = features.build(ohlcv, 25)
    assert np.isclose(f["R"][10], np.log(c[35] / c[10]))
    assert np.isnan(f["R"][-25:]).all() and np.isfinite(f["R"][:-25]).all()


def test_readout_learns_signal_and_quantiles_are_ordered() -> None:
    r = np.random.default_rng(5)
    x = r.standard_normal((3000, 5))
    y = 0.8 * x[:, 0] + r.standard_normal(3000) * 0.5
    tr = np.arange(2500)
    model, _ = fit_select(x, y, tr, horizon=5)
    q = model.predict(x[2500:])
    assert (np.diff(q, axis=1) >= 0).all()
    naive = np.tile(np.quantile(y[tr], QUANTILES), (500, 1))
    assert pinball(y[2500:], q).mean() < pinball(y[2500:], naive).mean()
