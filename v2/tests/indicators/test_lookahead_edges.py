"""Sin look-ahead (test de truncado) y casos borde de toda la biblioteca (T34)."""

from __future__ import annotations

import numpy as np
import pytest

from eim.core import Candle
from eim.indicators import SPECS, candle_arrays, compute
from eim.indicators.momentum import rsi, wr
from eim.indicators.volatility import boll
from eim.indicators.volume import mfi, vwap

H = 3_600_000


def _synthetic(n: int = 600, seed: int = 7) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.005, n))
    lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.005, n))
    v = rng.uniform(50, 150, n)
    return {"t": np.arange(n, dtype=np.int64) * H, "open": o, "high": h, "low": lo, "close": c,
            "volume": v, "taker_buy_v": v * rng.uniform(0.3, 0.7, n),
            "trades": rng.integers(100, 900, n).astype(float), "index": c * (1 - 1e-4)}


def _cut(d: dict[str, np.ndarray], k: int) -> dict[str, np.ndarray]:
    return {key: val[:k] for key, val in d.items()}


@pytest.mark.parametrize("ind", sorted(SPECS))
def test_no_lookahead_truncation(ind):
    """Serie completa y serie cortada dan el mismo valor en todos los puntos comunes."""
    d = _synthetic()
    full = compute(ind, d)
    for k in (150, 333, 599):
        part = compute(ind, _cut(d, k))
        for line, vals in part.items():
            np.testing.assert_array_equal(vals, full[line][:k], err_msg=f"{ind}.{line} k={k}")


@pytest.mark.parametrize("ind", sorted(SPECS))
def test_window_longer_than_data(ind):
    d = _cut(_synthetic(), 5)
    for line, vals in compute(ind, d).items():
        assert vals.shape == (5,), f"{ind}.{line}"


@pytest.mark.parametrize("ind", sorted(SPECS))
def test_empty_input(ind):
    for line, vals in compute(ind, _cut(_synthetic(), 0)).items():
        assert vals.shape == (0,), f"{ind}.{line}"


@pytest.mark.parametrize("ind", sorted(SPECS))
def test_nan_input_is_not_invented(ind):
    """Un NaN interior no rompe el cálculo ni se convierte en dato en ese punto."""
    d = _synthetic()
    hole = 300
    for key in ("open", "high", "low", "close", "volume", "taker_buy_v", "trades", "index"):
        d[key] = d[key].copy()
        d[key][hole] = np.nan
    out = compute(ind, d)
    for line, vals in out.items():
        assert vals.shape == (600,)
        assert np.isnan(vals[hole]), f"{ind}.{line} inventó un valor en el hueco"
        assert not np.isnan(vals[-1]) or ind in {"SAR"}, f"{ind}.{line} no se recupera"


def test_known_values_short_series():
    c = np.array([1.0, 2, 3, 4, 5])
    assert np.isnan(rsi(c, 14)).all()
    np.testing.assert_allclose(rsi(c, 2)[2:], 100.0)  # solo subidas
    flat = np.full(30, 10.0)
    np.testing.assert_allclose(rsi(flat, 14)[15:], 50.0)
    assert np.isnan(wr(flat, flat, flat, 14)).all()  # rango nulo → NaN
    b = boll(flat, 20)
    np.testing.assert_allclose(b["up"][19:], 10.0)
    np.testing.assert_allclose(b["dn"][19:], 10.0)


def test_zero_volume():
    n = 40
    h, lo, c = np.full(n, 11.0), np.full(n, 9.0), np.linspace(9.5, 10.5, n)
    z = np.zeros(n)
    assert np.isnan(mfi(h, lo, c, z, 14)).all()
    assert np.isnan(vwap(h, lo, c, z, np.arange(n) * H)).all()
    out = compute("EMV", {"high": h, "low": lo, "volume": z})
    assert np.isnan(out["emv"]).all()
    out = compute("TakerRatio", {"volume": z, "taker_buy_v": z})
    assert np.isnan(out["takerratio"]).all()


def test_vwap_resets_each_utc_day():
    n = 48
    t = np.arange(n, dtype=np.int64) * H
    p = np.r_[np.full(24, 10.0), np.full(24, 20.0)]
    out = vwap(p, p, p, np.ones(n), t)
    np.testing.assert_allclose(out[:24], 10.0)
    np.testing.assert_allclose(out[24:], 20.0)  # sin arrastre del día anterior


def test_candle_arrays_maps_missing_optional_fields_to_nan():
    cs = [Candle(t=0, o=1, h=2, l=0.5, c=1.5, v=10, taker_buy_v=6, trades=3),
          Candle(t=H, o=1.5, h=2, l=1, c=1.8, v=8)]
    d = candle_arrays(cs)
    assert d["taker_buy_v"][0] == 6 and np.isnan(d["taker_buy_v"][1])
    assert d["trades"][0] == 3 and np.isnan(d["trades"][1])
    out = compute("Delta", d)["delta"]
    assert out[0] == 2.0 and np.isnan(out[1])  # sin dato de taker → NaN, nunca supuesto
