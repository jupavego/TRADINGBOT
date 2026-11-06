"""Señales de las hipótesis de T139: funciones puras y causales sobre arreglos.

Cada función devuelve el lado (+1 largo, −1 corto, 0 nada) por vela del marco: el valor en `i` solo
usa datos conocidos al cierre de esa vela. Las ventanas de referencia excluyen la vela o la tasa
actual, y sin ventana suficiente no hay señal, nunca un cero disfrazado. Los parámetros llegan del
pre-registro: aquí no hay ninguno por defecto que se pueda ajustar sin dejar rastro.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from eim.core import Candle

DAY_MS = 86_400_000
MINUTES_PER_DAY = 1440
BARS_PER_DAY_4H = 6
ATR_PERIOD = 14                     # el de `paper.context`


def atr_series(h: np.ndarray, lo: np.ndarray, c: np.ndarray, period: int = ATR_PERIOD
               ) -> np.ndarray:
    """ATR de `paper.context` en cada vela: media simple de los últimos `period` rangos verdaderos,
    incluida la vela. NaN mientras no hay `period` velas."""
    n = len(c)
    out = np.full(n, np.nan)
    if n < period:
        return out
    prev = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - lo, np.maximum(np.abs(h - prev), np.abs(lo - prev)))
    out[period - 1:] = sliding_window_view(tr, period).mean(axis=1)
    return out


def imbalance(v: np.ndarray, taker: np.ndarray) -> np.ndarray:
    """Desequilibrio agresor de cada vela, en [−1, 1]: `2·taker_buy_v/v − 1`. NaN sin dato."""
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 2.0 * taker / v - 1.0
    out[~np.isfinite(out) | (v <= 0)] = np.nan
    return out


def flow_z(v: np.ndarray, taker: np.ndarray, sum_bars: int, window_bars: int,
           min_coverage: float) -> np.ndarray:
    """z del desequilibrio sumado en `sum_bars` velas contra las `window_bars` sumas anteriores.

    La ventana excluye la vela actual. Sin el `min_coverage` de la ventana con dato, o sin
    dispersión, es NaN.
    """
    n = len(v)
    z = np.full(n, np.nan)
    if n < sum_bars or n <= window_bars:
        return z
    s = np.full(n, np.nan)
    s[sum_bars - 1:] = sliding_window_view(imbalance(v, taker), sum_bars).sum(axis=1)
    ok = np.isfinite(s)
    x = np.where(ok, s, 0.0)
    c0 = np.concatenate(([0], np.cumsum(ok)))
    c1 = np.concatenate(([0.0], np.cumsum(x)))
    c2 = np.concatenate(([0.0], np.cumsum(x * x)))
    idx = np.arange(window_bars, n)
    count = c0[idx] - c0[idx - window_bars]
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = (c1[idx] - c1[idx - window_bars]) / count
        var = (c2[idx] - c2[idx - window_bars]) / count - mean * mean
        good = (count >= min_coverage * window_bars) & (var > 1e-12) & ok[idx]
        z[idx[good]] = (s[idx[good]] - mean[good]) / np.sqrt(var[good])
    return z


def flow_sides(z: np.ndarray, threshold: float) -> np.ndarray:
    """H2: a favor del flujo cuando |z| llega al umbral."""
    out = np.zeros(len(z), dtype=np.int8)
    out[z >= threshold] = 1
    out[z <= -threshold] = -1
    return out


def reversal_sides(z: np.ndarray, o: np.ndarray, c: np.ndarray, atr: np.ndarray,
                   threshold: float, min_move_atr: float) -> np.ndarray:
    """H3: en contra del flujo si la vela se movió ≥ `min_move_atr` ATR con el signo de z."""
    out = np.zeros(len(z), dtype=np.int8)
    move = c - o
    with np.errstate(invalid="ignore"):
        up = (z >= threshold) & (move >= min_move_atr * atr)
        down = (z <= -threshold) & (-move >= min_move_atr * atr)
    out[up] = -1
    out[down] = 1
    return out


def funding_sides(ft: np.ndarray, fr: np.ndarray, close_t: np.ndarray, bar_ms: int,
                  window_prints: int, q_low: float, q_high: float) -> np.ndarray:
    """H1: en contra de una tasa extrema, en la primera vela cuyo cierre es ≥ el pago.

    Estrictamente fuera de los percentiles de las `window_prints` tasas anteriores: la tasa suele
    quedarse en su valor base, y esos empates no son extremos. La hora del pago se trunca al minuto
    porque Binance la da con milisegundos sueltos. Un pago sin vela que cierre dentro de su marco
    (hueco en las velas) no da señal.
    """
    out = np.zeros(len(close_t), dtype=np.int8)
    for k in range(window_prints, len(fr)):
        prev = fr[k - window_prints:k]
        low, high = np.quantile(prev, [q_low, q_high])
        side = -1 if fr[k] > high else 1 if fr[k] < low else 0
        if side == 0:
            continue
        at = int(ft[k]) - int(ft[k]) % 60_000
        j = int(np.searchsorted(close_t, at, "left"))
        if j < len(close_t) and close_t[j] - at < bar_ms:
            out[j] = side
    return out


def cascade_minutes(t: np.ndarray, o: np.ndarray, h: np.ndarray, lo: np.ndarray, v: np.ndarray,
                    q_range: float, q_volume: float, window_days: int, min_coverage: float
                    ) -> np.ndarray:
    """H4: índices de las velas de 1 min que marcan cascada, en orden.

    Los umbrales se fijan al empezar cada día UTC con los `window_days` días anteriores, así que
    ninguna vela se juzga con datos de su propio día. Sin el `min_coverage` de la ventana, ese día
    no marca nada.
    """
    if not len(t):
        return np.array([], dtype=np.int64)
    with np.errstate(divide="ignore", invalid="ignore"):
        rng = (h - lo) / o
    need = min_coverage * window_days * MINUTES_PER_DAY
    hits: list[np.ndarray] = []
    for day in np.unique(t // DAY_MS):
        d0 = int(day) * DAY_MS
        a = int(np.searchsorted(t, d0 - window_days * DAY_MS))
        b = int(np.searchsorted(t, d0))
        e = int(np.searchsorted(t, d0 + DAY_MS))
        if b - a < need:
            continue
        qr = np.quantile(rng[a:b], q_range)
        qv = np.quantile(v[a:b], q_volume)
        got = np.nonzero((rng[b:e] >= qr) & (v[b:e] >= qv))[0]
        if len(got):
            hits.append(got + b)
    return np.concatenate(hits) if hits else np.array([], dtype=np.int64)


def cascade_sides(hits: np.ndarray, t: np.ndarray, o: np.ndarray, c: np.ndarray,
                  bar_t: np.ndarray, bar_ms: int) -> np.ndarray:
    """H4: en la vela del marco, en contra de la última vela de 1 min que marcó cascada.

    La vela de 1 min está dentro de la del marco, que cierra después. Si la última abrió y cerró
    igual, no hay sentido contra el que entrar y esa vela del marco no da señal.
    """
    out = np.zeros(len(bar_t), dtype=np.int8)
    for k in hits:
        j = int(np.searchsorted(bar_t, t[k], "right")) - 1
        if j < 0 or t[k] >= bar_t[j] + bar_ms:
            continue
        out[j] = -int(np.sign(c[k] - o[k]))
    return out


def momentum_sides(c: np.ndarray, lookback: int) -> np.ndarray:
    """H5: signo del retorno de `lookback` velas."""
    out = np.zeros(len(c), dtype=np.int8)
    if len(c) > lookback:
        out[lookback:] = np.sign(c[lookback:] - c[:-lookback]).astype(np.int8)
    return out


def daily_candles(candles_4h: Sequence[Candle]) -> list[Candle]:
    """Velas de 1 d agregadas de las de 4 h, solo con los días UTC completos (6 velas)."""
    days: dict[int, list[Candle]] = {}
    for x in candles_4h:
        days.setdefault(x.t // DAY_MS, []).append(x)
    out = []
    for d in sorted(days):
        xs = days[d]
        if len(xs) != BARS_PER_DAY_4H:
            continue
        taker = [x.taker_buy_v for x in xs]
        trades = [x.trades for x in xs]
        out.append(Candle(t=d * DAY_MS, o=xs[0].o, h=max(x.h for x in xs),
                          l=min(x.l for x in xs), c=xs[-1].c, v=sum(x.v for x in xs),
                          taker_buy_v=None if None in taker else sum(taker),
                          trades=None if None in trades else sum(trades)))
    return out
