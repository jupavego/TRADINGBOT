"""Variables ancladas a la sesión americana (T208): lo que un operador intradía mira del día.

Nada de esto mira el futuro: el valor en la vela `i` solo usa velas de su sesión hasta `i`
(inclusive, porque la señal se evalúa al cierre de `i`) o sesiones anteriores ya cerradas.
"""

from __future__ import annotations

import numpy as np

from eim.forge.session import Sessions


def _anchor_cumsum(x: np.ndarray, sid: np.ndarray) -> np.ndarray:
    """Suma acumulada que se reinicia en cada sesión (los tramos fuera de sesión son su grupo)."""
    cs = np.cumsum(np.where(np.isnan(x), 0.0, x))
    start = np.r_[True, sid[1:] != sid[:-1]]
    idx = np.maximum.accumulate(np.where(start, np.arange(len(sid)), 0))
    return cs - np.r_[0.0, cs][idx]


def session_vwap(h: np.ndarray, lo: np.ndarray, c: np.ndarray, v: np.ndarray,
                 s: Sessions) -> np.ndarray:
    """VWAP anclado a la apertura de la sesión americana (precio típico por volumen)."""
    tp = (h + lo + c) / 3
    num, den = _anchor_cumsum(tp * v, s.sid), _anchor_cumsum(v, s.sid)
    out = np.divide(num, den, out=np.full(len(c), np.nan), where=den > 0)
    out[s.sid < 0] = np.nan
    return out


def session_cvd(v: np.ndarray, tb: np.ndarray, s: Sessions) -> np.ndarray:
    """Delta acumulado de agresores de la sesión (compras − ventas a mercado)."""
    out = _anchor_cumsum(2 * tb - v, s.sid)
    out[s.sid < 0] = np.nan
    return out


def opening_range(h: np.ndarray, lo: np.ndarray, s: Sessions,
                  k: int) -> tuple[np.ndarray, np.ndarray]:
    """Máximo y mínimo de las primeras `k` velas de la sesión, disponibles solo tras cerrarlas."""
    hi = np.full(len(h), np.nan)
    lw = np.full(len(h), np.nan)
    for i0 in s.starts:
        i1 = int(s.last[int(i0)]) + 1
        a = int(i0) + k
        if a >= i1:
            continue
        hi[a:i1] = float(np.nanmax(h[int(i0):a]))
        lw[a:i1] = float(np.nanmin(lo[int(i0):a]))
    return hi, lw


def previous_session(h: np.ndarray, lo: np.ndarray, s: Sessions) -> tuple[np.ndarray, np.ndarray]:
    """Máximo y mínimo de la sesión anterior (cerrada), para cada vela de la sesión en curso."""
    hi = np.full(len(h), np.nan)
    lw = np.full(len(h), np.nan)
    prev: tuple[float, float] | None = None
    for i0 in s.starts:
        i1 = int(s.last[int(i0)]) + 1
        if prev is not None:
            hi[int(i0):i1], lw[int(i0):i1] = prev
        prev = (float(np.nanmax(h[int(i0):i1])), float(np.nanmin(lo[int(i0):i1])))
    return hi, lw


def bars_in_session(s: Sessions) -> np.ndarray:
    """Velas transcurridas desde la apertura de la sesión (0 = la de 09:30); −1 fuera."""
    out = np.full(len(s.sid), -1, dtype=np.int32)
    for i0 in s.starts:
        i1 = int(s.last[int(i0)]) + 1
        out[int(i0):i1] = np.arange(i1 - int(i0), dtype=np.int32)
    return out


def hourly_trend(t: np.ndarray, c: np.ndarray, n: int = 50) -> np.ndarray:
    """Lado de la tendencia de 1 h: signo de (cierre de 1 h − EMA n de 1 h), de la **última hora
    cerrada**, repetido en las velas de 5 m de la hora en curso (0 si aún no hay)."""
    from eim.indicators._core import ema

    hour = t // 3_600_000
    first = np.r_[True, hour[1:] != hour[:-1]]
    idx = np.flatnonzero(first)
    ends = np.r_[idx[1:], len(c)] - 1            # última vela de 5 m de cada hora
    hc = c[ends]
    e = ema(hc, n)
    side = np.sign(np.nan_to_num(hc - e, nan=0.0))
    out = np.zeros(len(c), dtype=float)
    for k in range(1, len(idx)):                  # la hora k usa el cierre de la k−1
        a = int(idx[k])
        b = int(idx[k + 1]) if k + 1 < len(idx) else len(c)
        out[a:b] = side[k - 1]
    return out
