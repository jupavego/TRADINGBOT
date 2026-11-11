"""T161: MinTRL, n a priori, SPA, MCS, bloque de Politis-White y Benjamini-Hochberg."""

import math

import numpy as np
import pytest

from eim.backtest.edge import bh, holm, sharpe_diff_pvalue
from eim.copytrading.stats import psr
from eim.validation.power import min_track_record, n_needed, power_row
from eim.validation.spa import DAY_MS, daily_matrix


@pytest.mark.parametrize("sr,sr0,skew,kurt", [(0.10, 0.0, 0.0, 3.0), (0.05, 0.0, -0.8, 7.0),
                                               (0.30, 0.10, 0.4, 4.0)])
def test_mintrl_is_where_psr_reaches_the_confidence(sr, sr0, skew, kurt):
    """Definición de Bailey y López de Prado: en n = MinTRL, PSR(sr0) = 1 − α exactamente."""
    n = min_track_record(sr, sr0, skew, kurt, alpha=0.05)
    assert psr(sr, sr0, math.ceil(n), skew, kurt) >= 0.95
    assert psr(sr, sr0, math.floor(n) - 1, skew, kurt) < 0.95
    assert psr(sr, sr0, n, skew, kurt) == pytest.approx(0.95, abs=1e-9)


def test_mintrl_normal_closed_form_and_edge_cases():
    # normal: 1 + (1 + SR²/2)·(z/SR)²; con SR = 0,1 y z = 1,6449 → ≈ 272,9
    assert min_track_record(0.1, 0.0) == pytest.approx(1 + 1.005 * (1.6448536 / 0.1) ** 2,
                                                       rel=1e-6)
    assert math.isinf(min_track_record(0.0, 0.0))
    assert math.isinf(min_track_record(0.05, 0.1))
    # cola izquierda gorda pide más historia
    assert min_track_record(0.1, 0.0, -1.0, 8.0) > min_track_record(0.1, 0.0)


def test_n_needed_matches_the_textbook_formula():
    # z_0,95 + z_0,80 = 1,6449 + 0,8416 = 2,4865; sd/edge = 10 → n ≈ 618,3
    assert n_needed(0.1, 1.0) == pytest.approx((2.4865 * 10) ** 2, rel=1e-3)
    assert math.isinf(n_needed(0.0, 1.0))


def test_power_row_reports_net_and_cost_thresholds():
    rng = np.random.default_rng(1)
    r = list(rng.normal(0.05, 1.0, 400))
    row = power_row(r, cost=0.2)
    assert row.n == 400 and row.sr is not None
    assert math.isinf(row.mintrl_cost)            # el bruto no supera el costo
    assert row.n_apriori == pytest.approx(n_needed(0.2, row.sd))
    js = row.to_json()
    assert js["mintrl_cost"] is None and isinstance(js["enough_zero"], bool)


def test_daily_matrix_sums_by_decision_day_and_fills_zeros():
    s = {"b": [(0, 1.0), (DAY_MS - 1, 0.5), (2 * DAY_MS, -1.0)], "a": [(5 * DAY_MS, 9.0)]}
    names, m = daily_matrix(s, 0, 3 * DAY_MS)
    assert names == ["a", "b"] and m.shape == (3, 2)
    assert m[:, 1].tolist() == [1.5, 0.0, -1.0]
    assert m[:, 0].sum() == 0.0                    # fuera de la ventana no cuenta


def test_bh_is_monotone_and_never_stricter_than_holm():
    p = {"a": 0.001, "b": 0.02, "c": 0.03, "d": 0.5}
    adj, hl = bh(p), holm(p)
    assert adj["a"] == pytest.approx(0.004)
    assert adj["b"] == pytest.approx(0.04) and adj["c"] == pytest.approx(0.04)
    assert adj["d"] == pytest.approx(0.5)
    assert all(adj[k] <= hl[k] + 1e-12 for k in p)


def test_sharpe_diff_default_block_is_unchanged():
    rng = np.random.default_rng(3)
    a, b = rng.normal(0.001, 0.01, 300), rng.normal(0.0, 0.01, 300)
    assert sharpe_diff_pvalue(a, b, 365) == sharpe_diff_pvalue(a, b, 365, block=17)


arch = pytest.importorskip("arch")


def test_spa_rejects_nothing_on_pure_noise_and_finds_a_real_edge():
    from eim.validation.spa import spa_test

    rng = np.random.default_rng(7)
    noise = rng.normal(0.0, 1.0, (800, 9))
    res = spa_test([f"r{i}" for i in range(9)], noise, reps=500, seed=1)
    assert res.p_consistent > 0.05
    assert res.p_lower <= res.p_consistent <= res.p_upper
    edge = noise.copy()
    edge[:, 4] += 0.25
    res2 = spa_test([f"r{i}" for i in range(9)], edge, reps=500, seed=1)
    assert res2.best == "r4" and res2.p_consistent < 0.01


def test_mcs_keeps_not_trading_when_nothing_beats_it():
    from eim.validation.spa import mcs

    rng = np.random.default_rng(11)
    g = rng.normal(-0.3, 1.0, (600, 4))
    g[:, 0] = rng.normal(0.0, 1.0, 600)
    p = mcs(["a", "b", "c", "d"], g, reps=500, seed=2)
    assert p["no_operar"] >= 0.10
    assert p["b"] < 0.10


def test_block_length_grows_with_persistence():
    from eim.validation.spa import block_length

    rng = np.random.default_rng(5)
    e = rng.normal(size=2000)
    ar = np.zeros(2000)
    for i in range(1, 2000):
        ar[i] = 0.8 * ar[i - 1] + e[i]
    assert block_length(ar) > block_length(e) >= 1.0
    p_auto, _ = sharpe_diff_pvalue(e, ar, 365, n_boot=200, block="auto")
    assert 0.0 < p_auto <= 1.0


def test_mcs_with_aliases_survives_two_models_with_identical_losses():
    """T166: un etiquetador que se queda en un solo estado da el mismo pronóstico que no tener
    régimen; `mcs_losses` dividía por una varianza nula y abortaba."""
    from eim.validation.spa import mcs_losses, mcs_with_aliases

    rng = np.random.default_rng(166)
    base = rng.gamma(2.0, 0.2, (400, 3))
    losses = np.column_stack([base, base[:, 0]])     # la cuarta es copia exacta de la primera
    names = ["u0", "m0", "good", "clone"]
    # La versión sin alias no lo aguanta: `arch` 8.0.0 divide por una varianza nula y se queda sin
    # candidatos que eliminar. Se aceptan varios tipos porque el fallo es interno de la biblioteca.
    with pytest.raises((IndexError, ValueError, ZeroDivisionError)):
        mcs_losses(names, losses, 0.10, 200, 1)
    p, alias = mcs_with_aliases(names, losses, 0.10, 200, 1)
    assert alias == {"clone": "u0"}
    assert p["clone"] == p["u0"]
    assert set(p) == set(names)
    assert all(0.0 <= v <= 1.0 for v in p.values())


def test_mcs_with_aliases_matches_mcs_losses_when_nothing_repeats():
    from eim.validation.spa import mcs_losses, mcs_with_aliases

    rng = np.random.default_rng(167)
    losses = rng.gamma(2.0, 0.2, (400, 3))
    losses[:, 1] += 0.4
    names = ["a", "b", "c"]
    p, alias = mcs_with_aliases(names, losses, 0.10, 200, 3)
    assert alias == {}
    assert p == mcs_losses(names, losses, 0.10, 200, 3)
