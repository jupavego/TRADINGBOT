"""Rasgos del día, estados causales y condicionamiento (T166).

Lo que se fija aquí es lo único que puede invalidar la comparación pre-registrada sin que se note:
una fuga de información del futuro. Cada pieza se prueba recortando la serie y exigiendo que lo
ya calculado no cambie. Sin red y sin disco.
"""

from __future__ import annotations

import numpy as np

from eim.agents.regime import daily
from eim.agents.regime.params import RegimeParams

MIN = 60_000
DAY = daily.DAY_MS


def _one_minute_days(n_days: int, seed: int = 1) -> dict[str, np.ndarray]:
    """Velas de 1 min completas de `n_days` días, con volatilidad que cambia a la mitad."""
    rng = np.random.default_rng(seed)
    n = n_days * 1440
    sd = np.where(np.arange(n) // 1440 < n_days // 2, 0.0002, 0.0012)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0, sd)))
    t = np.arange(n, dtype=np.int64) * MIN
    o = np.concatenate(([c[0]], c[:-1]))
    return {"t": t, "o": o, "h": np.maximum(o, c) * 1.0001, "l": np.minimum(o, c) * 0.9999,
            "c": c}


def test_day_extras_reproduces_the_definitions_by_hand():
    """Un día de 3 velas con números redondos: eficiencia y rango salen de la definición."""
    t = np.array([0, MIN, 2 * MIN], dtype=np.int64)
    o = np.array([100.0, 110.0, 105.0])
    c = np.array([110.0, 105.0, 115.0])
    hi = np.array([112.0, 111.0, 116.0])
    lo = np.array([99.0, 104.0, 104.0])
    r = daily.day_extras(t, o, hi, lo, c)
    # pasos = |110−100| + |105−110| + |115−105| = 25; |115 − 100| / 25 = 0,6
    assert r["er"][0] == 0.6
    assert r["rng"][0] == (116.0 - 99.0) / 100.0


def test_expanding_z_only_looks_backwards():
    x = np.random.default_rng(2).normal(size=(200, 3))
    full = daily.expanding_z(x)
    for cut in (40, 100, 199):
        assert np.allclose(daily.expanding_z(x[:cut]), full[:cut], equal_nan=True)
    assert np.isnan(full[: daily.MIN_Z_DAYS]).all()
    assert np.isfinite(full[daily.MIN_Z_DAYS:]).all()


def test_forecast_next_is_the_unconditional_when_there_is_one_state():
    ln_rv = np.log(np.random.default_rng(3).lognormal(-8.0, 0.5, size=120))
    one = daily.forecast_next(np.zeros(120, dtype=np.int16), ln_rv, 0)
    assert np.isnan(one[0])
    # el día i usa solo los días < i: a mano para i = 50
    m, v = ln_rv[:50].mean(), ln_rv[:50].var()
    assert abs(one[50] - float(np.exp(m + v / 2))) < 1e-9


def test_forecast_next_falls_back_while_a_state_is_thin():
    """Un estado con menos de `MIN_STATE_DAYS` días no se usa: se cae al suelo incondicional."""
    ln_rv = np.linspace(-9.0, -7.0, 200)
    st = np.zeros(200, dtype=np.int16)
    st[::50] = 1                       # el estado 1 nunca junta 20 días
    h = daily.forecast_next(st, ln_rv)
    for i in (51, 101, 151):           # el día siguiente a un día en el estado flaco
        m, v = ln_rv[:i].mean(), ln_rv[:i].var()
        assert abs(h[i] - float(np.exp(m + v / 2))) < 1e-12
    # y el estado gordo sí usa su propio grupo, que no es el de todos los días
    fat = ln_rv[:121][st[:121] == 0]
    assert abs(h[121] - float(np.exp(fat.mean() + fat.var() / 2))) < 1e-12


def test_forecast_next_does_not_look_at_the_future():
    rng = np.random.default_rng(4)
    ln_rv = np.log(rng.lognormal(-8.0, 0.6, size=300))
    st = (np.arange(300) // 60 % 2).astype(np.int16)
    full = daily.forecast_next(st, ln_rv)
    for cut in (80, 150, 299):
        assert np.allclose(daily.forecast_next(st[:cut], ln_rv[:cut]), full[:cut],
                           equal_nan=True)


def test_the_conditional_forecast_beats_the_floor_when_the_state_is_real():
    """Cordura de la métrica: con un régimen de volatilidad de verdad, la QLIKE condicional baja."""
    from eim.forecast.vol_eval import qlike

    rng = np.random.default_rng(5)
    st = (np.arange(600) // 100 % 2).astype(np.int16)
    ln_rv = np.where(st == 1, -7.0, -9.0) + rng.normal(0.0, 0.3, size=600)
    rv = np.exp(ln_rv)
    cond = daily.forecast_next(st, ln_rv)
    floor = daily.forecast_next(np.zeros(600, dtype=np.int16), ln_rv, 0)
    m = np.isfinite(cond) & np.isfinite(floor)
    assert qlike(rv[m], cond[m]).mean() < qlike(rv[m], floor[m]).mean()


def test_jump_and_hmm_states_are_stable_on_the_prefix():
    """Recortar la serie no cambia los estados ya asignados hasta el último reajuste cabido."""
    x = np.random.default_rng(6).normal(size=(240, 4))
    x[120:, 0] += 2.5
    for fn in (lambda z: daily.jump_states(z, 60, 2, 2.0, 20),
               lambda z: daily.hmm_states(z, 60, 2, 20)):
        full = fn(x)
        for cut in (100, 160, 220):
            got = fn(x[:cut])
            assert np.array_equal(got[:cut - (cut - 60) % 20], full[:cut - (cut - 60) % 20])


def test_bocpd_states_are_stable_on_the_prefix_and_label_the_last_day():
    ret = np.random.default_rng(7).normal(0.0, 0.01, size=200)
    ret[120:] += 0.03
    full = daily.bocpd_states(ret, min_bars=40)
    assert (full[:40] == -1).all()
    assert (full[40:] >= 0).all()
    for cut in (60, 120, 199):
        assert np.array_equal(daily.bocpd_states(ret[:cut], min_bars=40), full[:cut])


def test_bocpd_states_use_the_agent_parameters():
    """La referencia es el BOCPD de producción: sus parámetros salen de `RegimeParams`."""
    ret = np.random.default_rng(8).normal(0.0, 0.01, size=150)
    assert np.array_equal(daily.bocpd_states(ret), daily.bocpd_states(ret, RegimeParams()))
    assert (daily.bocpd_states(ret)[: RegimeParams().min_bars] == -1).all()


def test_persistence_counts_what_it_says():
    st = np.array([0, 0, 0, 1, 1, 0, 0], dtype=np.int16)
    p = daily.persistence(st)
    assert p["n"] == 7
    assert p["n_switches"] == 2
    assert abs(p["dwell_mean"] - 7 / 3) < 1e-12
    assert p["occupancy"][0] > p["occupancy"][1]
    assert daily.persistence(np.full(50, 0, dtype=np.int16))["n_switches"] == 0


def test_the_whole_daily_pipeline_runs_on_synthetic_candles():
    from eim.forecast import vol_models as vm

    d = _one_minute_days(80, seed=9)
    ds = vm.daily_series(d["t"], d["c"])
    ex = daily.day_extras(d["t"], d["o"], d["h"], d["l"], d["c"])
    assert np.array_equal(ds["day"], ex["day"])
    ok = ds["ok"] & np.isfinite(ds["ret"]) & np.isfinite(ex["er"])
    raw = np.column_stack([ds["ret"][ok], np.log(ds["rv"][ok]), ex["er"][ok], ex["rng"][ok]])
    z = daily.expanding_z(raw)
    z = z[np.isfinite(z).all(axis=1)]
    st = daily.jump_states(z, 20, 2, 2.0, 20)
    assert (st[20:] >= 0).all()
    assert daily.persistence(st)["dwell_mean"] is not None
