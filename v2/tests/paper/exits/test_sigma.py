"""T132 — los estimadores de volatilidad: que midan lo que dicen y que no miren al futuro.

Las pruebas que importan son tres: (1) sobre una serie con volatilidad conocida, cada estimador la
recupera; (2) el valor de la vela `j` no cambia si se alteran las velas posteriores (sin
anticipación); (3) donde falta ventana sale `nan`, nunca 0 — un σ de 0 pondría el stop encima del
precio, y la regla de T129 es que la falta de datos **no aprieta**.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.paper.exits import harrv, sigma

TRUE_SIGMA = 0.004
N = 4000
WINDOW = 100
ESTIMATORS = ("close_to_close", "parkinson", "garman_klass", "rogers_satchell", "yang_zhang")


def ohlc(n: int = N, s: float = TRUE_SIGMA, seed: int = 7, drift: float = 0.0,
         px0: float = 70_000.0):
    """OHLC de un paseo geométrico con σ conocida por vela; el rango sale de un puente simulado.

    Los subpasos tienen que ser bastantes: con pocos, el máximo y el mínimo muestreados quedan por
    dentro de los continuos y los estimadores de rango salen sesgados a la baja (Rogers–Satchell es
    el más sensible). Con 60 el sesgo de discretización baja del 5 %.
    """
    rng = np.random.default_rng(seed)
    steps = 60                                    # subpasos por vela: dan máximo y mínimo
    sub = rng.normal(drift / steps, s / np.sqrt(steps), (n, steps))
    walk = px0 * np.exp(np.cumsum(sub.ravel()))
    m = walk.reshape(n, steps)
    o = np.concatenate(([px0], m[:-1, -1]))
    c = m[:, -1]
    h = np.maximum(m.max(axis=1), np.maximum(o, c))
    lo = np.minimum(m.min(axis=1), np.minimum(o, c))
    return o, h, lo, c


@pytest.mark.parametrize("name", ESTIMATORS)
def test_each_estimator_recovers_a_known_volatility(name: str):
    o, h, lo, c = ohlc()
    s = sigma.of(name, o, h, lo, c, WINDOW)
    got = float(np.nanmedian(s[WINDOW + 20:]))
    assert got == pytest.approx(TRUE_SIGMA, rel=0.25), f"{name}: {got:.5f}"


@pytest.mark.parametrize("name", ESTIMATORS)
def test_the_range_based_estimators_are_more_efficient_than_close_to_close(name: str):
    """Con la misma ventana, el rango estima σ con menos dispersión que el cierre a cierre."""
    if name == "close_to_close":
        pytest.skip("es la referencia")
    o, h, lo, c = ohlc()
    a = sigma.of("close_to_close", o, h, lo, c, WINDOW)[WINDOW + 20:]
    b = sigma.of(name, o, h, lo, c, WINDOW)[WINDOW + 20:]
    assert float(np.nanstd(b)) < float(np.nanstd(a))


def test_yang_zhang_survives_a_drift_that_fools_close_to_close_less():
    """Yang–Zhang es insesgado con deriva: con tendencia fuerte sigue cerca de la σ real."""
    o, h, lo, c = ohlc(drift=0.004)               # deriva del tamaño de la propia σ
    yz = float(np.nanmedian(sigma.of("yang_zhang", o, h, lo, c, WINDOW)[WINDOW + 20:]))
    assert yz == pytest.approx(TRUE_SIGMA, rel=0.3)


@pytest.mark.parametrize("name", [*ESTIMATORS, "atr14"])
def test_no_estimator_looks_at_the_future(name: str):
    """El valor de la vela j no cambia si se reescriben las velas posteriores."""
    o, h, lo, c = ohlc(n=600)
    j = 400
    base = sigma.of(name, o, h, lo, c, WINDOW)[j]
    o2, h2, lo2, c2 = (x.copy() for x in (o, h, lo, c))
    o2[j + 1:] *= 3.0
    h2[j + 1:] *= 3.5
    lo2[j + 1:] *= 2.5
    c2[j + 1:] *= 3.0
    assert sigma.of(name, o2, h2, lo2, c2, WINDOW)[j] == pytest.approx(base, rel=1e-12)


@pytest.mark.parametrize("name", ESTIMATORS)
def test_missing_window_is_nan_and_never_zero(name: str):
    o, h, lo, c = ohlc(n=60)
    s = sigma.of(name, o, h, lo, c, WINDOW)
    assert np.isnan(s).all(), f"{name} inventó un valor sin ventana"
    short = sigma.of(name, *ohlc(n=300), WINDOW)
    assert np.isnan(short[:10]).all()
    assert not np.any(short[np.isfinite(short)] == 0.0)


def test_the_atr_window_is_its_own_period_not_the_shared_one():
    """El ATR no usa la ventana común: tiene su periodo de Wilder, y antes de él es `nan`."""
    s = sigma.of("atr14", *ohlc(n=60), WINDOW)
    assert np.isnan(s[:sigma.ATR_PERIOD]).all()
    assert np.isfinite(s[sigma.ATR_PERIOD:]).all()
    assert np.isnan(sigma.of("atr14", *ohlc(n=10), WINDOW)).all()


def test_a_bar_with_invalid_prices_does_not_poison_the_whole_series():
    o, h, lo, c = ohlc(n=400)
    h2 = h.copy()
    h2[200] = np.nan
    s = sigma.of("parkinson", o, h2, lo, c, WINDOW)
    assert np.isnan(s[200])                        # su ventana queda invalidada
    assert np.isfinite(s[200 + WINDOW + 1])        # y la serie se recupera después


def test_an_unknown_estimator_fails_with_the_list_of_options():
    with pytest.raises(ValueError, match="desconocido"):
        sigma.of("magia", *ohlc(n=50), WINDOW)


def test_atr_uses_the_previous_close_in_the_true_range():
    """Un salto entre velas cuenta en el ATR aunque la vela sea estrecha."""
    n = 40
    o = np.full(n, 100.0)
    h, lo, c = o.copy() + 0.1, o.copy() - 0.1, o.copy()
    o2, h2, lo2, c2 = (x.copy() for x in (o, h, lo, c))
    for k in range(20, n):                         # salto de 10 puntos y vela estrecha
        o2[k] = h2[k] = lo2[k] = c2[k] = 110.0
        h2[k] += 0.1
        lo2[k] -= 0.1
    quiet = sigma.of("atr14", o, h, lo, c, 20)[-1]
    jumpy = sigma.of("atr14", o2, h2, lo2, c2, 20)[-1]
    assert jumpy > quiet


# --- HAR-RV -----------------------------------------------------------------------------
MIN_DAYS = 20
BARS_PER_DAY = 96.0


def fine(days: int, per_day: int = 1440, s: float = 0.0005, seed: int = 11):
    """Velas finas sintéticas: `days` días completos de 1 min."""
    rng = np.random.default_rng(seed)
    n = days * per_day
    t = np.arange(n, dtype=np.int64) * 60_000
    c = 70_000.0 * np.exp(np.cumsum(rng.normal(0.0, s, n)))
    return t, c


def test_the_daily_realized_volatility_matches_the_simulated_one():
    t, c = fine(40)
    keys, rv = harrv.daily_rv(t, c)
    assert len(keys) == 40
    # RV diaria ≈ 1440·σ²; σ por minuto 0,0005
    assert float(np.median(rv)) == pytest.approx(1440 * 0.0005**2, rel=0.25)


def test_the_jump_between_days_does_not_enter_the_realized_volatility():
    t, c = fine(10)
    c2 = c.copy()
    c2[5 * 1440:] *= 1.5                           # salto enorme al empezar el día 6
    _, rv = harrv.daily_rv(t, c)
    _, rv2 = harrv.daily_rv(t, c2)
    assert rv2 == pytest.approx(rv, rel=1e-9)      # el primer retorno del día no cruza la frontera


def test_the_forecast_only_uses_earlier_days():
    t, c = fine(80)
    keys, rv = harrv.daily_rv(t, c)
    pred = harrv.forecast_by_day(keys, rv, MIN_DAYS)
    rv2 = rv.copy()
    rv2[60:] *= 9.0                                # se reescribe el futuro
    pred2 = harrv.forecast_by_day(keys, rv2, MIN_DAYS)
    for d in list(keys[:60]):
        if int(d) in pred and int(d) in pred2:
            assert pred[int(d)] == pytest.approx(pred2[int(d)], rel=1e-12)


def test_there_is_no_forecast_until_there_are_enough_days():
    t, c = fine(30)
    keys, rv = harrv.daily_rv(t, c)
    pred = harrv.forecast_by_day(keys, rv, MIN_DAYS)
    assert all(int(d) not in pred for d in keys[:MIN_DAYS])
    assert harrv.forecast_by_day(keys, rv, 1000) == {}


def test_sigma_by_bar_is_relative_per_bar_and_nan_where_there_is_no_forecast():
    t, c = fine(80)
    path_t = np.arange(80 * BARS_PER_DAY, dtype=np.int64) * (15 * 60_000)
    s = harrv.sigma_by_bar(path_t, t, c, BARS_PER_DAY, MIN_DAYS)
    assert np.isnan(s[:int(MIN_DAYS * BARS_PER_DAY)]).all()
    good = s[np.isfinite(s)]
    assert len(good) > 100
    # σ por vela de 15 m ≈ σ_minuto·√15 = 0,0005·√15
    assert float(np.median(good)) == pytest.approx(0.0005 * np.sqrt(15), rel=0.3)
    assert not np.any(good <= 0.0)


def test_sigma_by_bar_without_fine_candles_says_nothing():
    path_t = np.arange(100, dtype=np.int64) * (15 * 60_000)
    s = harrv.sigma_by_bar(path_t, np.array([], dtype=np.int64), np.array([]), BARS_PER_DAY)
    assert np.isnan(s).all()
    assert len(harrv.daily_rv(np.array([0]), np.array([1.0]))[0]) == 0
