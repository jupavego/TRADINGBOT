"""T139: las señales son causales, callan sin dato y hacen lo que dice el pre-registro."""

from __future__ import annotations

import numpy as np
import pytest

from eim.agents.levels.pivots import atr
from eim.core import Candle
from eim.validation.hypotheses import signals as sg

H = 3_600_000
DAY = 24 * H
W = 240                    # ventana de las pruebas de flujo, en velas


def _flow(n: int = 600, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    v = rng.uniform(50, 150, n)
    return v, v * rng.uniform(0.35, 0.65, n)


# --- ATR ---------------------------------------------------------------------------------------
def test_atr_is_the_one_of_paper_context():
    rng = np.random.default_rng(1)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
    h, lo = c * 1.003, c * 0.997
    got = sg.atr_series(h, lo, c)
    assert np.isnan(got[12]) and np.isfinite(got[13])
    for i in (50, 150, 299):
        s = max(0, i - 200)
        assert got[i] == pytest.approx(atr(h[s:i + 1], lo[s:i + 1], c[s:i + 1], 14), abs=1e-9)


# --- flujo --------------------------------------------------------------------------------------
def test_flow_z_excludes_the_current_bar_and_has_no_lookahead():
    v, tk = _flow()
    base = sg.flow_z(v, tk, 4, W, 0.9)
    assert np.isnan(base[W - 1]) and np.isfinite(base[W + 5])
    for i in (W + 3, 400, 590):
        v2, tk2 = v.copy(), tk.copy()
        tk2[i + 1:] = v2[i + 1:]            # el futuro cambia por completo
        assert sg.flow_z(v2, tk2, 4, W, 0.9)[i] == pytest.approx(base[i], abs=1e-12)


def test_flow_z_matches_its_definition():
    v, tk = _flow()
    z = sg.flow_z(v, tk, 4, W, 0.9)
    imb = 2 * tk / v - 1
    s = np.convolve(imb, np.ones(4), "full")[:len(imb)]
    i = 500
    prev = s[i - W:i]
    assert z[i] == pytest.approx((s[i] - prev.mean()) / prev.std(), abs=1e-9)


def test_flow_z_needs_coverage_and_never_invents_data():
    v, tk = _flow()
    tk[100:160] = np.nan                    # 25 % de la ventana sin dato
    z = sg.flow_z(v, tk, 4, W, 0.9)
    assert np.isnan(z[300]) and np.isnan(z[120])
    assert np.isfinite(z[500])
    assert np.isnan(sg.imbalance(np.array([0.0]), np.array([0.0]))[0])


def test_flow_sides_and_reversal_only_with_a_big_move_of_the_same_sign():
    z = np.array([2.5, -2.5, 1.0, 2.5, np.nan])
    assert sg.flow_sides(z, 2.0).tolist() == [1, -1, 0, 1, 0]
    o = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
    c = np.array([102.0, 98.0, 102.0, 100.5, 102.0])
    a = np.full(5, 1.0)
    # sube con flujo comprador → corto; baja con flujo vendedor → largo; sin z o sin ATR, nada
    assert sg.reversal_sides(z, o, c, a, 2.0, 1.0).tolist() == [-1, 1, 0, 0, 0]
    assert sg.reversal_sides(z, o, c, np.full(5, np.nan), 2.0, 1.0).tolist() == [0] * 5
    # una vela contraria al flujo no es el movimiento que se revierte
    assert sg.reversal_sides(np.array([2.5]), np.array([100.0]), np.array([98.0]),
                             np.array([1.0]), 2.0, 1.0).tolist() == [0]


# --- funding --------------------------------------------------------------------------------------
def _prints(n: int = 400) -> tuple[np.ndarray, np.ndarray]:
    t = np.arange(n, dtype=np.int64) * 8 * H
    rng = np.random.default_rng(2)
    return t, rng.normal(0.0001, 0.0001, n)


def _bars(n_prints: int, bar: int) -> np.ndarray:
    return np.arange(n_prints * 8 * H // bar, dtype=np.int64) * bar + bar


def test_funding_goes_against_the_extreme_on_the_bar_that_closes_at_the_print():
    t, r = _prints()
    r[350] = 0.01
    r[360] = -0.01
    close = _bars(400, H)
    s = sg.funding_sides(t, r, close, H, 270, 0.1, 0.9)
    assert s[np.searchsorted(close, t[350])] == -1
    assert s[np.searchsorted(close, t[360])] == 1
    assert close[np.searchsorted(close, t[350])] == t[350]


def test_funding_pegged_at_its_base_rate_is_not_an_extreme():
    """Con ≥ o ≤, cada tasa en su valor base contaría como extrema: es la razón de lo estricto."""
    t = np.arange(400, dtype=np.int64) * 8 * H
    r = np.full(400, 0.0001)
    r[::9] = 0.00005                        # p10 por debajo; el p90 es el propio valor base
    s = sg.funding_sides(t, r, _bars(400, H), H, 270, 0.1, 0.9)
    assert (s == -1).sum() == 0


def test_funding_millisecond_offset_keeps_the_same_bar_and_a_hole_gives_nothing():
    t, r = _prints()
    r[350] = 0.01
    close = _bars(400, 4 * H)
    a = sg.funding_sides(t, r, close, 4 * H, 270, 0.1, 0.9)
    t2 = t.copy()
    t2[350] += 3                            # Binance da la hora con milisegundos sueltos
    assert (sg.funding_sides(t2, r, close, 4 * H, 270, 0.1, 0.9) == a).all()
    hole = close[(close < t[350]) | (close >= t[350] + 8 * H)]
    assert (sg.funding_sides(t, r, hole, 4 * H, 270, 0.1, 0.9)[-1:] == 0).all()
    assert sg.funding_sides(t[:270], r[:270], close, 4 * H, 270, 0.1, 0.9).sum() == 0


def test_funding_uses_only_previous_prints():
    t, r = _prints()
    close = _bars(400, H)
    base = sg.funding_sides(t, r, close, H, 270, 0.1, 0.9)
    r2 = r.copy()
    r2[351:] = 1.0
    other = sg.funding_sides(t, r2, close, H, 270, 0.1, 0.9)
    j = int(np.searchsorted(close, t[350]))
    assert (other[:j + 1] == base[:j + 1]).all()


# --- cascada ----------------------------------------------------------------------------------
def _minutes(days: int = 100, seed: int = 3):
    n = days * sg.MINUTES_PER_DAY
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=np.int64) * 60_000
    o = np.full(n, 100.0)
    r = rng.uniform(0.0005, 0.001, n)
    v = rng.uniform(1, 2, n)
    return t, o, o * (1 + r), o.copy(), o * (1 + r / 2), v


def test_cascade_needs_range_and_volume_and_thresholds_come_from_previous_days():
    t, o, h, lo, c, v = _minutes()
    k = 95 * sg.MINUTES_PER_DAY + 30
    h[k], v[k] = 200.0, 500.0
    hits = sg.cascade_minutes(t, o, h, lo, v, 0.999, 0.99, 90, 0.9)
    assert k in hits.tolist()
    v2 = v.copy()
    v2[k] = 1.0
    assert k not in sg.cascade_minutes(t, o, h, lo, v2, 0.999, 0.99, 90, 0.9).tolist()
    # Una cascada hoy no mueve los umbrales de hoy: los fija el día anterior
    h3, v3 = h.copy(), v.copy()
    k2 = k + 5
    h3[k2], v3[k2] = 200.0, 500.0
    assert k in sg.cascade_minutes(t, o, h3, lo, v3, 0.999, 0.99, 90, 0.9).tolist()


def test_cascade_is_silent_without_the_window():
    t, o, h, lo, c, v = _minutes(days=60)
    h[-5], v[-5] = 200.0, 500.0
    assert len(sg.cascade_minutes(t, o, h, lo, v, 0.999, 0.99, 90, 0.9)) == 0
    assert len(sg.cascade_minutes(t[:0], o[:0], h[:0], lo[:0], v[:0], 0.999, 0.99, 90, 0.9)) == 0


def test_cascade_side_goes_against_the_last_marked_minute_of_the_bar():
    t = np.array([10, 20, 70, 100, 130, 300], dtype=np.int64) * 60_000
    o = np.full(6, 100.0)
    c = np.array([99.0, 101.0, 100.0, 99.0, 100.0, 99.0])
    bar_t = np.array([0, 60, 120], dtype=np.int64) * 60_000
    s = sg.cascade_sides(np.arange(6), t, o, c, bar_t, H)
    # 1.ª vela: la última sube → corto. 2.ª: tras una sin sentido, la última baja → largo.
    # 3.ª: la única abre y cierra igual → nada. La del minuto 300 no cae en ninguna vela.
    assert s.tolist() == [-1, 1, 0]
    # Una que abre y cierra igual, si es la última de su vela, deja esa vela sin señal
    assert sg.cascade_sides(np.array([3, 2]), t, o, c, bar_t, H).tolist() == [0, 0, 0]


# --- momento y 1 d ----------------------------------------------------------------------------
def test_momentum_is_the_sign_of_the_lookback_return():
    c = np.array([1.0, 2.0, 3.0, 2.5, 2.0, 2.0])
    assert sg.momentum_sides(c, 2).tolist() == [0, 0, 1, 1, -1, -1]
    assert sg.momentum_sides(c, 10).tolist() == [0] * 6


def test_daily_candles_only_with_full_days():
    def bar(t: int, x: float) -> Candle:
        return Candle(t=t, o=x, h=x + 1, l=x - 1, c=x + 0.5, v=2.0, taker_buy_v=1.0, trades=3)
    day0 = [bar(k * 4 * H, 100.0 + k) for k in range(6)]
    day1 = [bar(DAY + k * 4 * H, 200.0) for k in range(5)]        # le falta una vela
    got = sg.daily_candles(day0 + day1)
    assert len(got) == 1
    d = got[0]
    assert (d.t, d.o, d.h, d.l, d.c) == (0, 100.0, 106.0, 99.0, 105.5)
    assert (d.v, d.taker_buy_v, d.trades) == (12.0, 6.0, 18)
