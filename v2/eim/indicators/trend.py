"""Familia tendencia: MA, EMA, WMA, SAR parabólico, SuperTrend (SUPER), DMI/ADX."""

from __future__ import annotations

import numpy as np

from eim.indicators._core import ArrayLike, arr, div, ema, rma, shift, sma, wma
from eim.indicators.volatility import atr, true_range


def ma(close: ArrayLike, periods: tuple[int, ...] = (7, 25, 99)) -> dict[str, np.ndarray]:
    """MA de Binance: una SMA por período (por defecto 7, 25, 99)."""
    return {f"ma{n}": sma(close, n) for n in periods}


def ema_lines(close: ArrayLike, periods: tuple[int, ...] = (7, 25, 99),
              seed: str = "first") -> dict[str, np.ndarray]:
    """EMA de Binance: una EMA por período (sembrada en el primer dato, como el FRM)."""
    return {f"ema{n}": ema(close, n, seed) for n in periods}


def wma_lines(close: ArrayLike, periods: tuple[int, ...] = (7, 25, 99)) -> dict[str, np.ndarray]:
    """WMA de Binance: una media ponderada lineal por período."""
    return {f"wma{n}": wma(close, n) for n in periods}


def sar(high: ArrayLike, low: ArrayLike, start: float = 0.02, step: float = 0.02,
        maximum: float = 0.2) -> np.ndarray:
    """SAR parabólico de Wilder.

    Dirección inicial (como TA-Lib): larga si h₁−h₀ > l₀−l₁, si no corta; SAR inicial = l₀
    (larga) o h₀ (corta). El SAR nunca penetra el rango de las dos velas previas.
    """
    h, lo = arr(high), arr(low)
    n = len(h)
    out = np.full(n, np.nan)
    if n < 2 or np.isnan(h[:2]).any() or np.isnan(lo[:2]).any():
        return out
    long = (h[1] - h[0]) > (lo[0] - lo[1])
    s = lo[0] if long else h[0]
    ep = h[1] if long else lo[1]
    af = start
    out[1] = s
    for i in range(2, n):
        if h[i] != h[i] or lo[i] != lo[i]:
            continue
        s = s + af * (ep - s)
        if long:
            s = min(s, lo[i - 1], lo[i - 2])
            if lo[i] < s:  # giro a corto
                long, s, ep, af = False, ep, lo[i], start
            elif h[i] > ep:
                ep, af = h[i], min(af + step, maximum)
        else:
            s = max(s, h[i - 1], h[i - 2])
            if h[i] > s:  # giro a largo
                long, s, ep, af = True, ep, h[i], start
            elif lo[i] < ep:
                ep, af = lo[i], min(af + step, maximum)
        out[i] = s
    return out


def supertrend(high: ArrayLike, low: ArrayLike, close: ArrayLike, n: int = 10,
               k: float = 3.0) -> dict[str, np.ndarray]:
    """SuperTrend: bandas hl2 ± k·ATR(n, Wilder) con arrastre; `dir` = +1 alcista, −1 bajista."""
    h, lo, c = arr(high), arr(low), arr(close)
    a = atr(h, lo, c, n)
    mid = (h + lo) / 2
    bu, bl = mid + k * a, mid - k * a
    m = len(c)
    line, direction = np.full(m, np.nan), np.full(m, np.nan)
    fu = fl = np.nan
    d = 1.0
    for i in range(m):
        if np.isnan(bu[i]) or np.isnan(c[i]):
            continue
        prev_c = c[i - 1] if i > 0 else np.nan
        if np.isnan(fu):
            fu, fl = bu[i], bl[i]
            d = 1.0 if c[i] >= mid[i] else -1.0
        else:
            fu = bu[i] if (bu[i] < fu or prev_c > fu) else fu
            fl = bl[i] if (bl[i] > fl or prev_c < fl) else fl
            if d < 0 and c[i] > fu:
                d = 1.0
            elif d > 0 and c[i] < fl:
                d = -1.0
        line[i] = fl if d > 0 else fu
        direction[i] = d
    return {"st": line, "dir": direction}


def dmi(high: ArrayLike, low: ArrayLike, close: ArrayLike, n: int = 14,
        m: int = 6) -> dict[str, np.ndarray]:
    """DMI de Wilder: PDI/MDI con suavizado Wilder(n), ADX = Wilder(DX, m), ADXR."""
    h, lo, c = arr(high), arr(low), arr(close)
    up, down = h - shift(h, 1), shift(lo, 1) - lo
    pdm = np.where((up > down) & (up > 0), up, 0.0)
    mdm = np.where((down > up) & (down > 0), down, 0.0)
    nan_row = np.isnan(up) | np.isnan(down)
    pdm[nan_row] = np.nan
    mdm[nan_row] = np.nan
    tr = true_range(h, lo, c)
    tr[:1] = np.nan  # la primera vela no tiene cierre previo
    s_tr, s_p, s_m = (np.concatenate([[np.nan], rma(x[1:], n)]) if len(x) else x
                      for x in (tr, pdm, mdm))
    pdi, mdi = 100 * div(s_p, s_tr), 100 * div(s_m, s_tr)
    dx = 100 * div(np.abs(pdi - mdi), pdi + mdi)
    first = np.flatnonzero(~np.isnan(dx))
    adx = np.full(len(c), np.nan)
    if len(first):
        f = int(first[0])
        adx[f:] = rma(dx[f:], m)
    adxr = (adx + shift(adx, m)) / 2
    return {"pdi": pdi, "mdi": mdi, "adx": adx, "adxr": adxr}
