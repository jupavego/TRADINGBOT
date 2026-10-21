"""Indicadores de `trendrider` con la definición de TA-Lib (la biblioteca de la estrategia).

EMA/RSI/SMA salen de `eim.indicators`; aquí lo que ese módulo define distinto: ADX/±DI de Wilder
(`PLUS_DI`/`ADX` de TA-Lib, no el DMI de Binance), MACD, BBANDS (σ poblacional), OBV y la agregación
a marcos superiores. Funciones puras sobre arreglos, NaN durante el calentamiento.
"""

from __future__ import annotations

import numpy as np

from eim.indicators._core import ema, rolling_std, sma

NAN = np.nan


def adx_di(h: np.ndarray, lo: np.ndarray, c: np.ndarray, n: int = 14
           ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(ADX, +DI, −DI) de Wilder como TA-Lib: sumas suavizadas sembradas con las n primeras."""
    size = len(c)
    adx, pdi, mdi = (np.full(size, NAN) for _ in range(3))
    if size <= 2 * n:
        return adx, pdi, mdi
    up, dn = h[1:] - h[:-1], lo[:-1] - lo[1:]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum.reduce([h[1:] - lo[1:], np.abs(h[1:] - c[:-1]), np.abs(lo[1:] - c[:-1])])
    sp, sm, st = pdm[:n].sum(), mdm[:n].sum(), tr[:n].sum()
    dx = np.full(size, NAN)
    for i in range(n, size):
        if i > n:
            sp, sm, st = sp - sp / n + pdm[i - 1], sm - sm / n + mdm[i - 1], st - st / n + tr[i - 1]
        if st:
            pdi[i], mdi[i] = 100 * sp / st, 100 * sm / st
            tot = pdi[i] + mdi[i]
            dx[i] = 100 * abs(pdi[i] - mdi[i]) / tot if tot else 0.0
        else:
            pdi[i] = mdi[i] = dx[i] = 0.0
    adx[2 * n - 1] = dx[n:2 * n].mean()
    for i in range(2 * n, size):
        adx[i] = (adx[i - 1] * (n - 1) + dx[i]) / n
    return adx, pdi, mdi


def macd(c: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
         ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    line = ema(c, fast, "sma") - ema(c, slow, "sma")
    sig = ema(line, signal, "sma")
    return line, sig, line - sig


def bbands(c: np.ndarray, n: int = 20, k: float = 2.0
           ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mid, sd = sma(c, n), rolling_std(c, n, ddof=0)
    return mid + k * sd, mid, mid - k * sd


def obv(c: np.ndarray, v: np.ndarray) -> np.ndarray:
    out = np.empty(len(c))
    out[0] = v[0]
    step = np.where(c[1:] > c[:-1], v[1:], np.where(c[1:] < c[:-1], -v[1:], 0.0))
    out[1:] = v[0] + np.cumsum(step)
    return out


class Informative:
    """Velas agregadas a un marco superior, solo grupos completos, con su cierre."""

    def __init__(self, t, o, h, lo, c, step: int, base: int) -> None:
        self.step, self.base = step, base
        key = t // step * step
        need = step // base
        starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
        ends = np.r_[starts[1:], len(t)]
        ok = [(a, b) for a, b in zip(starts, ends, strict=True)
              if b - a == need and t[b - 1] - t[a] == (need - 1) * base]
        self.t = np.array([key[a] for a, _ in ok], dtype=np.int64)
        self.o = np.array([o[a] for a, _ in ok])
        self.c = np.array([c[b - 1] for _, b in ok])
        self.h = np.array([h[a:b].max() for a, b in ok])
        self.l = np.array([lo[a:b].min() for a, b in ok])   # noqa: E741

    def align(self, series: np.ndarray, t: np.ndarray) -> np.ndarray:
        """Valor de la última vela superior CERRADA al cierre de cada vela base
        (`merge_informative_pair`: fecha + marco superior − marco base ≤ apertura de la vela)."""
        idx = np.searchsorted(self.t + self.step - self.base, t, side="right") - 1
        out = np.full(len(t), NAN)
        good = idx >= 0
        out[good] = series[idx[good]]
        return out


def informative(t, o, h, lo, c, step: int, base: int = 3_600_000) -> Informative:
    return Informative(np.asarray(t), o, h, lo, c, step, base)
