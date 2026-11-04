"""T132 — `ExitFeatures` v1: swings confirmados, marco mayor causal y cobertura declarada.

Las dos pruebas que importan: un swing no existe hasta que lo confirman las velas posteriores, y
la dirección del marco mayor en una vela del camino solo usa velas mayores **ya cerradas**. Si
cualquiera de las dos fallara, M3 y M7 estarían mirando al futuro.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.paper.engine import Path
from eim.paper.exits import features
from tests.paper.exits.helpers import coherent_path
from tests.paper.helpers import T0, bar

M15 = 900_000
H1 = 3_600_000


def test_a_swing_appears_only_when_the_later_bars_confirm_it():
    """Un fractal de 5 tiene 2 velas a cada lado: el pivote en `i` se conoce al cerrar `i+2`."""
    lows = [10.0, 9.0, 5.0, 9.5, 10.5, 11.0, 12.0]       # el mínimo está en el índice 2
    highs = [x + 1 for x in lows]
    s_lo, _ = features.swings(np.array(highs), np.array(lows), 5)
    assert np.isnan(s_lo[3]), "no puede conocerse antes de su confirmación"
    assert s_lo[4] == pytest.approx(5.0)                  # confirmado al cerrar i+2
    assert s_lo[5] == pytest.approx(5.0)                  # y se conserva


def test_a_swing_never_changes_when_the_future_is_rewritten():
    p, _ = coherent_path(200, seed=3)
    s_lo, s_hi = features.swings(p.h, p.l, 5)
    j = 120
    h2, l2 = p.h.copy(), p.l.copy()
    h2[j + 1:] *= 4.0
    l2[j + 1:] *= 0.25
    again_lo, again_hi = features.swings(h2, l2, 5)
    assert again_lo[j] == pytest.approx(s_lo[j], nan_ok=True)
    assert again_hi[j] == pytest.approx(s_hi[j], nan_ok=True)


def test_a_short_path_has_no_swings():
    s_lo, s_hi = features.swings(np.array([1.0, 2.0]), np.array([1.0, 2.0]), 5)
    assert np.isnan(s_lo).all() and np.isnan(s_hi).all()


def test_the_higher_timeframe_direction_uses_only_closed_higher_bars():
    """La vela de 1 h se conoce al cerrar: una vela de 15 m dentro de ella usa la 1 h ANTERIOR."""
    n = 80
    up = np.linspace(100.0, 200.0, n)
    htf = Path([bar(T0 + k * H1, float(up[k]), float(up[k]) + 1, float(up[k]) - 1,
                    float(up[k])) for k in range(n)], (), H1)
    path_t = np.array([T0 + k * M15 for k in range(n * 4)], dtype=np.int64)
    closes = np.full(len(path_t), 150.0)
    d = features.htf_direction(path_t, closes, htf)
    # la primera vela del camino cae ANTES de que cierre la primera de 1 h: sin dato
    assert d[0] == 0
    # dentro de la hora k, la dirección es la de la hora k−1 (la última cerrada)
    own = features._dir_of(htf.c, features.EMA_FAST, features.EMA_SLOW)
    for k in range(2, n):
        for m in range(4):
            assert d[k * 4 + m] == own[k - 1], (k, m)


def test_without_the_higher_timeframe_the_substitute_is_declared():
    p, _ = coherent_path(300, seed=5)
    f = features.build(p, "parkinson", swing_bars=5)
    assert "SUSTITUTO" in f.source["htf_dir"]
    htf = Path([bar(int(p.t[k * 4]), float(p.o[k * 4]), float(p.h[k * 4]), float(p.l[k * 4]),
                    float(p.c[k * 4])) for k in range(len(p.t) // 4)], (), 4 * M15)
    g = features.build(p, "parkinson", swing_bars=5, htf=htf)
    assert "SUSTITUTO" not in g.source["htf_dir"] and "marco mayor" in g.source["htf_dir"]


def test_the_features_declare_their_real_coverage():
    p, fine = coherent_path(400, seed=7)
    f = features.build(p, "parkinson", swing_bars=5, fine=fine)
    j = f.to_json()
    assert set(j["coverage"]) == {"sigma_abs", "swing_low", "swing_high", "htf_dir", "bar_range"}
    assert 0.0 <= j["coverage"]["sigma_abs"] <= 1.0
    assert j["version"] == features.VERSION and j["sigma"] == "parkinson"
    assert all(f.source[k] for k in f.source)


def test_harrv_without_fine_candles_says_so_and_stays_nan():
    p, _ = coherent_path(300, seed=9)
    f = features.build(p, features.HARRV, swing_bars=5, fine=None)
    assert np.isnan(f.sigma_abs).all()
    assert "sin velas de 1 min" in f.source["sigma_abs"]
    assert f.coverage["sigma_abs"] == 0.0


def test_the_median_range_is_the_noise_unit_and_is_causal():
    p, _ = coherent_path(300, seed=11)
    r = features.median_range(p.h, p.l, p.c, window=50)
    assert np.isnan(r[:49]).all()
    j = 200
    h2, l2 = p.h.copy(), p.l.copy()
    h2[j + 1:] *= 5.0
    assert features.median_range(h2, l2, p.c, window=50)[j] == pytest.approx(r[j])


def test_the_ema_starts_at_the_first_simple_mean_and_is_nan_before():
    x = np.arange(1.0, 21.0)
    e = features.ema(x, 5)
    assert np.isnan(e[:4]).all()
    assert e[4] == pytest.approx(3.0)                     # media simple de 1..5
    assert np.isnan(features.ema(np.array([1.0, 2.0]), 5)).all()
