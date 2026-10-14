"""Familia momentum: MACD, RSI, KDJ, StochRSI, WR, CCI, MTM, TRIX."""

from __future__ import annotations

import numpy as np

from eim.indicators._core import (
    ArrayLike,
    arr,
    div,
    ema,
    recursive,
    rma,
    rolling_mad,
    rolling_max,
    rolling_min,
    shift,
    sma,
)


def macd(close: ArrayLike, fast: int = 12, slow: int = 26,
         signal: int = 9) -> dict[str, np.ndarray]:
    """MACD: DIF = EMA(fast) − EMA(slow); DEA = EMA(DIF, signal); hist = DIF − DEA.

    EMAs sembradas en el primer dato (convención Binance/FRM). Algunos gráficos chinos
    dibujan la barra como 2·(DIF − DEA); aquí `hist` es la diferencia sin escalar.
    """
    c = arr(close)
    dif = ema(c, fast) - ema(c, slow)
    dea = ema(dif, signal)
    return {"dif": dif, "dea": dea, "hist": dif - dea}


def rsi(close: ArrayLike, n: int = 14) -> np.ndarray:
    """RSI de Wilder (medias sembradas con SMA, como TA-Lib).

    Sin pérdidas → 100; sin ganancias → 0; sin movimiento alguno → 50.
    """
    c = arr(close)
    if len(c) < 2:
        return np.full(len(c), np.nan)
    d = np.diff(c)
    hole = np.isnan(d)
    g = rma(np.where(hole, np.nan, np.maximum(d, 0.0)), n)
    lo = rma(np.where(hole, np.nan, np.maximum(-d, 0.0)), n)
    total = g + lo
    out = 100 * div(g, total)
    out[(total == 0)] = 50.0
    return np.concatenate([[np.nan], out])


def rsi_lines(close: ArrayLike, periods: tuple[int, ...] = (6, 12, 24)) -> dict[str, np.ndarray]:
    """RSI de Binance: una línea por período (por defecto 6, 12, 24)."""
    return {f"rsi{n}": rsi(close, n) for n in periods}


def kdj(high: ArrayLike, low: ArrayLike, close: ArrayLike, n: int = 9, m1: int = 3,
        m2: int = 3) -> dict[str, np.ndarray]:
    """KDJ: RSV = (C − LLV(L,n)) / (HHV(H,n) − LLV(L,n))·100.

    K = SMA(RSV, m1, 1) y D = SMA(K, m2, 1) (suavizado tipo Wilder, sembrados en 50);
    J = 3K − 2D. Rango nulo → RSV NaN (K y D conservan su valor).
    """
    h, lo, c = arr(high), arr(low), arr(close)
    ll, hh = rolling_min(lo, n), rolling_max(h, n)
    rsv = 100 * div(c - ll, hh - ll)
    k = recursive(rsv, 1.0 / m1, seed=50.0)
    d = recursive(k, 1.0 / m2, seed=50.0)
    return {"k": k, "d": d, "j": 3 * k - 2 * d}


def stochrsi(close: ArrayLike, n_rsi: int = 14, n_stoch: int = 14, k: int = 3,
             d: int = 3) -> dict[str, np.ndarray]:
    """StochRSI: estocástico (0–100) del RSI; K = SMA(·, k), D = SMA(K, d). Rango nulo → NaN."""
    r = rsi(close, n_rsi)
    ll, hh = rolling_min(r, n_stoch), rolling_max(r, n_stoch)
    st = 100 * div(r - ll, hh - ll)
    kk = sma(st, k)
    return {"k": kk, "d": sma(kk, d)}


def wr(high: ArrayLike, low: ArrayLike, close: ArrayLike, n: int = 14) -> np.ndarray:
    """Williams %R en −100..0: (HHV − C)/(HHV − LLV)·(−100). Rango nulo → NaN."""
    h, lo, c = arr(high), arr(low), arr(close)
    hh, ll = rolling_max(h, n), rolling_min(lo, n)
    return -100 * div(hh - c, hh - ll)


def cci(high: ArrayLike, low: ArrayLike, close: ArrayLike, n: int = 14) -> np.ndarray:
    """CCI: (TP − SMA(TP)) / (0.015 · desviación media). TP = (h+l+c)/3. Desviación 0 → NaN."""
    tp = (arr(high) + arr(low) + arr(close)) / 3
    return div(tp - sma(tp, n), 0.015 * rolling_mad(tp, n))


def mtm(close: ArrayLike, n: int = 12, m: int = 6) -> dict[str, np.ndarray]:
    """Momentum: MTM = C − C[n]; MAMTM = SMA(MTM, m)."""
    c = arr(close)
    x = c - shift(c, n)
    return {"mtm": x, "mamtm": sma(x, m)}


def trix(close: ArrayLike, n: int = 12, m: int = 9) -> dict[str, np.ndarray]:
    """TRIX: variación % de la triple EMA(n); MATRIX = SMA(TRIX, m)."""
    tr = ema(ema(ema(arr(close), n), n), n)
    prev = shift(tr, 1)
    x = 100 * div(tr - prev, prev)
    return {"trix": x, "matrix": sma(x, m)}
