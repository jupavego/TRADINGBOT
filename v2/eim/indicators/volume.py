"""Familia volumen: VOL, OBV, MFI, EMV, VWAP por sesión, AVL (precio medio acumulado)."""

from __future__ import annotations

import numpy as np

from eim.indicators._core import ArrayLike, arr, div, rolling_sum, shift, sma

DAY_MS = 86_400_000


def vol(volume: ArrayLike, periods: tuple[int, ...] = (5, 10)) -> dict[str, np.ndarray]:
    """VOL de Binance: volumen y sus medias simples (por defecto 5 y 10)."""
    v = arr(volume)
    return {"vol": v, **{f"ma{n}": sma(v, n) for n in periods}}


def obv(close: ArrayLike, volume: ArrayLike, m: int = 30) -> dict[str, np.ndarray]:
    """OBV acumulado desde el inicio de la serie (OBV₀ = V₀, como TA-Lib); MAOBV = SMA(m).

    Es acumulativo: su nivel depende del inicio de la serie; comparar solo variaciones.
    """
    c, v = arr(close), arr(volume)
    step = np.sign(c - shift(c, 1)) * v
    if len(step):
        step[0] = v[0]
    hole = np.isnan(step)
    out = np.cumsum(np.where(hole, 0.0, step))
    out[hole] = np.nan
    return {"obv": out, "maobv": sma(out, m)}


def mfi(high: ArrayLike, low: ArrayLike, close: ArrayLike, volume: ArrayLike,
        n: int = 14) -> np.ndarray:
    """Money Flow Index. Flujo positivo si TP sube, negativo si baja.

    Sin flujo negativo → 100; sin flujo alguno (volumen 0) → NaN.
    """
    tp = (arr(high) + arr(low) + arr(close)) / 3
    mf = tp * arr(volume)
    dtp = tp - shift(tp, 1)
    pos = np.where(np.isnan(dtp), np.nan, np.where(dtp > 0, mf, 0.0))
    neg = np.where(np.isnan(dtp), np.nan, np.where(dtp < 0, mf, 0.0))
    sp, sn = rolling_sum(pos, n), rolling_sum(neg, n)
    return 100 * div(sp, sp + sn)


def emv(high: ArrayLike, low: ArrayLike, volume: ArrayLike, n: int = 14,
        m: int = 9) -> dict[str, np.ndarray]:
    """Ease of Movement (fórmula de los gráficos de origen chino que usa Binance).

    VOLUME = MA(V,n)/V; MID = 100·(H+L − REF(H+L,1))/(H+L);
    EMV = MA(MID·VOLUME·(H−L)/MA(H−L,n), n); MAEMV = MA(EMV, m). Volumen 0 → NaN.
    """
    h, lo, v = arr(high), arr(low), arr(volume)
    hl = h + lo
    vol_ratio = div(sma(v, n), v)
    mid = 100 * div(hl - shift(hl, 1), hl)
    rng = h - lo
    x = sma(mid * vol_ratio * div(rng, sma(rng, n)), n)
    return {"emv": x, "maemv": sma(x, m)}


def _anchored(pv: np.ndarray, v: np.ndarray, group: np.ndarray | None) -> np.ndarray:
    hole = np.isnan(pv) | np.isnan(v)
    cpv = np.cumsum(np.where(hole, 0.0, pv))
    cv = np.cumsum(np.where(hole, 0.0, v))
    if group is not None and len(group):
        start = np.r_[True, group[1:] != group[:-1]]
        idx = np.maximum.accumulate(np.where(start, np.arange(len(group)), 0))
        cpv = cpv - np.r_[0.0, cpv][idx]
        cv = cv - np.r_[0.0, cv][idx]
    out = div(cpv, cv)
    out[hole] = np.nan
    return out


def vwap(high: ArrayLike, low: ArrayLike, close: ArrayLike, volume: ArrayLike,
         t: ArrayLike, period_ms: int = DAY_MS) -> np.ndarray:
    """VWAP con reinicio por sesión (por defecto día UTC). `t` en ms epoch.

    Precio típico (h+l+c)/3. Sesión aún sin volumen → NaN.
    """
    tp = (arr(high) + arr(low) + arr(close)) / 3
    v = arr(volume)
    group = np.asarray(t, dtype=np.int64) // int(period_ms)
    return _anchored(tp * v, v, group)


def avl(high: ArrayLike, low: ArrayLike, close: ArrayLike, volume: ArrayLike) -> np.ndarray:
    """AVL (línea de precio medio): Σ(TP·V)/ΣV acumulado desde el inicio de la serie cargada.

    Equivale a un VWAP anclado en la primera vela; depende de dónde empieza la serie.
    """
    tp = (arr(high) + arr(low) + arr(close)) / 3
    v = arr(volume)
    return _anchored(tp * v, v, None)
