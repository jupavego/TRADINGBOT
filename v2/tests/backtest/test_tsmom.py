"""Integridad de la cartera continua de T163: señal causal, σ, pesos, costos y funding."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np

from eim.backtest.params import ZERO_COSTS, CostParams
from eim.backtest.tsmom import (
    DAY_MS,
    TsmomParams,
    buy_and_hold_weight,
    no_vol_target_weight,
    realized_vol,
    run_portfolio,
    target_weight,
    trend_signal,
    weekday,
)
from eim.core import Candle

P = TsmomParams()
EPOCH = date(1970, 1, 1).toordinal()


def days(n: int, first: str = "2021-01-04") -> np.ndarray:
    """`n` días epoch consecutivos desde `first` (2021-01-04 fue lunes)."""
    d0 = date.fromisoformat(first).toordinal() - EPOCH
    return np.arange(d0, d0 + n, dtype=np.int64)


def bar(price: float, rng: float = 0.0, v: float = 1e9) -> Candle:
    return Candle(t=0, o=price, h=price * (1 + rng), l=price * (1 - rng), c=price, v=v)


def test_weekday_cuadra_con_el_calendario():
    for iso in ("2021-01-04", "2024-02-29", "2026-11-09", "2026-11-05"):
        d = date.fromisoformat(iso).toordinal() - EPOCH
        assert int(weekday(np.array([d]))[0]) == datetime.fromisoformat(iso).weekday()


def test_trend_signal_es_causal_y_acotada():
    c = np.exp(np.linspace(0, 1, 200))                  # subida monótona
    s = trend_signal(c, P.lookbacks)
    assert np.all(np.isnan(s[:max(P.lookbacks)]))       # calentamiento
    assert np.allclose(s[max(P.lookbacks):], 1.0)
    assert np.allclose(trend_signal(1 / c, P.lookbacks)[max(P.lookbacks):], -1.0)
    # cambiar el futuro no cambia el pasado
    c2 = c.copy()
    c2[150:] *= 3.0
    assert np.allclose(s[:150], trend_signal(c2, P.lookbacks)[:150], equal_nan=True)
    assert set(np.unique(s[max(P.lookbacks):])) <= {-1.0, -1 / 3, 1 / 3, 1.0}


def test_realized_vol_es_la_desviacion_anualizada():
    rng = np.random.default_rng(163)
    r = rng.normal(0, 0.02, 300)
    v = realized_vol(r, P.vol_window, P.year_days)
    assert np.all(np.isnan(v[:P.vol_window - 1]))
    i = 199
    esperado = float(np.std(r[i - P.vol_window + 1:i + 1], ddof=1)) * np.sqrt(P.year_days)
    assert abs(v[i] - esperado) < 1e-12


def test_target_weight_recorta_y_respeta_el_signo():
    s = np.array([1.0, -1.0, 1 / 3, np.nan])
    v = np.array([0.02, 0.60, 0.60, 0.60])              # la primera σ es diminuta → recorte
    w = target_weight(s, v, P)
    assert w[0] == P.max_leverage
    assert w[1] < 0 and abs(w[1]) < P.max_leverage
    assert abs(w[2] - (1 / 3) * P.vol_target / 0.60) < 1e-12
    assert np.isnan(w[3])
    assert np.allclose(buy_and_hold_weight(w)[:3], 1.0) and np.isnan(buy_and_hold_weight(w)[3])
    assert np.allclose(no_vol_target_weight(s, v)[:3], s[:3])


def _run(n=40, w=1.0, prices=None, cp=ZERO_COSTS, funding=None, fprice=None, start=1, **kw):
    d = days(n)
    px = np.full(n, 100.0) if prices is None else np.asarray(prices, float)
    ws = np.full(n, w)
    bars = [bar(p) for p in px]
    f = np.zeros((0, 2)) if funding is None else np.asarray(funding, float)
    fp = np.zeros(0) if fprice is None else np.asarray(fprice, float)
    return run_portfolio(d, px, px, ws, bars, f, fp, TsmomParams(**kw), cp, start=start)


def test_sin_costos_el_precio_plano_no_mueve_el_capital():
    out = _run()
    assert out["ruined"] is False
    assert np.allclose(out["equity"][1:], P.initial_equity)
    assert np.allclose(out["ret"][2:], 0.0)
    assert out["fees"].sum() == 0.0 and out["slip"].sum() == 0.0


def test_el_peso_se_cumple_y_el_retorno_es_el_del_precio_por_el_peso():
    px = 100.0 * np.cumprod(np.r_[1.0, np.full(39, 1.01)])
    out = _run(prices=px, w=2.0)
    i = 10                                              # día sin rebalanceo (no es lunes)
    assert not out["rebalance"][i]
    esperado = out["qty"][i] * (px[i] - px[i - 1]) / out["equity"][i - 1]
    assert abs(out["ret"][i] - esperado) < 1e-12
    # el lunes el nocional vuelve al peso objetivo sobre el capital del momento de ejecutar
    j = int(np.flatnonzero(out["rebalance"])[2])
    eq_exec = out["equity"][j - 1] + out["qty"][j - 1] * (px[j] - px[j - 1])
    assert abs(out["qty"][j] * px[j] / eq_exec - 2.0) < 1e-9


def test_los_costos_solo_pueden_restar():
    px = 100.0 * np.cumprod(np.r_[1.0, 1 + np.sin(np.arange(39)) / 50])
    bruto = _run(prices=px, w=2.0, cp=ZERO_COSTS)
    neto = _run(prices=px, w=2.0, cp=CostParams())
    assert neto["fees"].sum() > 0 and neto["slip"].sum() > 0
    assert neto["equity"][-1] < bruto["equity"][-1]
    quieto = ~neto["rebalance"]
    quieto[1] = False                                              # el día `start` abre posición
    assert np.all(neto["traded"][quieto] == 0.0)                   # solo se opera al rebalancear


def test_funding_se_cobra_con_el_signo_del_motor():
    d = days(10)
    t = int(d[5]) * DAY_MS + 8 * 3_600_000             # un punto de funding dentro del día 5
    out = _run(funding=[[t, 0.0001]], fprice=[100.0])
    esperado = out["qty"][5] * 100.0 * 0.0001
    assert abs(out["funding"][5] - esperado) < 1e-12 and esperado > 0
    assert abs(out["equity"][5] - (out["equity"][4] - esperado)) < 1e-9
    corto = _run(w=-1.0, funding=[[t, 0.0001]], fprice=[100.0])
    assert corto["funding"][5] < 0                     # el corto cobra


def test_no_hay_look_ahead_en_el_capital():
    px = 100.0 * np.cumprod(np.r_[1.0, 1 + np.cos(np.arange(39)) / 40])
    base = _run(prices=px, w=1.5, cp=CostParams())
    px2 = px.copy()
    px2[25:] *= 5.0
    alt = _run(prices=px2, w=1.5, cp=CostParams())
    assert np.allclose(base["equity"][1:25], alt["equity"][1:25], equal_nan=True)


def test_la_ruina_para_la_simulacion():
    px = np.r_[np.full(5, 100.0), np.full(35, 1.0)]     # −99 % de golpe
    out = _run(prices=px, w=3.0)
    assert out["ruined"] is True
    assert np.isnan(out["equity"][-1])
