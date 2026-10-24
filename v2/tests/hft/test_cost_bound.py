"""Cota analítica de costos (T77): movimientos y techo con previsión perfecta, sin red."""

from __future__ import annotations

import numpy as np
import pytest

from eim.hft.cost_bound import asof_grid, bound_table, mid_moves_bps, spread_summary


def test_mid_moves_are_exact_on_a_regular_series():
    t = np.arange(0, 100_000, 1_000)
    mid = 100.0 * 1.0001 ** np.arange(t.size)             # +1 pb compuesto por segundo
    d = mid_moves_bps(t, mid, 5_000)
    assert d.size == t.size - 5                            # al final no se acorta el horizonte
    assert np.allclose(d, (1.0001 ** 5 - 1) * 1e4)


def test_mid_moves_skip_stale_targets_and_collection_gaps():
    t = np.array([0, 1_000, 2_000, 20_000, 21_000, 22_000])   # hueco de 18 s
    mid = np.array([100, 100, 100, 200, 200, 200], dtype=float)
    d = mid_moves_bps(t, mid, 1_000)
    assert d.size == 4 and np.all(d == 0)                 # nunca cruza el hueco
    assert mid_moves_bps(t[:1], mid[:1], 1_000).size == 0


def test_asof_grid_takes_last_price_and_drops_stale_points():
    t = np.array([100, 900, 1_500, 9_000])
    p = np.array([1.0, 2.0, 3.0, 4.0])
    gt, gp = asof_grid(t, p, step_ms=1_000, max_age_ms=5_000)
    assert gt.tolist() == [1_000, 2_000, 3_000, 4_000, 5_000, 6_000, 9_000]
    assert gp.tolist() == [2.0, 3.0, 3.0, 3.0, 3.0, 3.0, 4.0]   # 7 000 y 8 000: precio viejo


def test_bound_table_ceiling_and_fractions():
    t = np.arange(0, 61_000, 1_000)
    mid = np.where(np.arange(t.size) % 2 == 0, 100.0, 100.12)     # saltos de ~12 pb cada 1 s
    res = bound_table(t, mid, horizons_s=(1, 2), costs_bps={"taker": 10.0})
    one, two = res["horizons"]["1"], res["horizons"]["2"]
    assert one["frac_gt_taker"] == 1.0
    assert one["ceiling_taker"] == pytest.approx(12 - 10, abs=0.05)
    assert two["mean"] == 0 and two["ceiling_taker"] == 0         # vuelve al mismo precio
    assert res["points"] == t.size and res["hours"] == pytest.approx(60 / 3600, abs=0.01)


def test_spread_summary():
    s = spread_summary([99.99] * 3, [100.01] * 3)
    assert s["p50"] == pytest.approx(2.0, abs=1e-3)
    assert spread_summary([], []) == {}
