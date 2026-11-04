"""Estimadores de volatilidad con velas para las salidas de T132 (§7 de `T129_sl_dinamico.md`).

Todos devuelven un arreglo alineado con el camino: el valor en el índice `j` se calcula **solo con
velas ≤ j**, así que una política puede leerlo en la vela `j` sin anticipación. Donde no hay
ventana completa va `nan`, que las políticas tratan como «sin dato» y nunca como 0 (un σ de 0
pondría el stop encima del precio: la regla es que falta de datos **no aprieta**).

Unidad: **σ relativo por vela del camino** (fracción del precio). Una política que quiera el stop a
`k·σ` en precio multiplica por el precio de referencia. Se eligió relativo porque es lo único
comparable entre 2023 (BTC a 16 000) y 2026, y porque el riesgo de las ideas también es relativo.

Estimadores (los cuatro últimos usan el rango de la vela, mucho más eficiente que el cierre a
cierre; Yang–Zhang además es insesgado con deriva y con saltos de apertura):

- `atr_rel`: ATR de Wilder dividido por el cierre (el que ya usa el proyecto en `agents/levels`).
- `close_to_close`: desviación típica de los log-retornos de cierre. Es la referencia pobre.
- `parkinson`: Parkinson (1980), solo máximo y mínimo.
- `garman_klass`: Garman y Klass (1980), añade apertura y cierre.
- `rogers_satchell`: Rogers y Satchell (1991), robusto a la deriva; es la pieza de Yang–Zhang.
- `yang_zhang`: Yang y Zhang (2000), combina apertura, cierre y Rogers–Satchell.

Puro: numpy, sin dependencias nuevas (◆5 de T129).
"""

from __future__ import annotations

import numpy as np

MIN_WINDOW = 2
ATR_PERIOD = 14
YZ_K_NUM = 0.34          # k = 0,34 / (1,34 + (n+1)/(n−1)), de Yang y Zhang (2000)
YZ_K_DEN = 1.34


def _roll_mean(x: np.ndarray, n: int) -> np.ndarray:
    """Media móvil causal de ventana `n`: el valor en j usa x[j−n+1 … j]. `nan` antes."""
    out = np.full(len(x), np.nan)
    if n < 1 or len(x) < n:
        return out
    c = np.concatenate(([0.0], np.nancumsum(x)))
    ok = np.concatenate(([0], np.cumsum(~np.isnan(x)).astype(np.int64)))
    tot = c[n:] - c[:-n]
    cnt = ok[n:] - ok[:-n]
    out[n - 1:] = np.where(cnt == n, tot / n, np.nan)
    return out


def _safe_log(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """log(a/b) con `nan` donde alguno no es positivo (nunca lanza ni devuelve ±inf)."""
    ok = (a > 0) & (b > 0) & np.isfinite(a) & np.isfinite(b)
    out = np.full(len(a), np.nan)
    np.log(np.where(ok, a, 1.0) / np.where(ok, b, 1.0), out=out, where=ok)
    return out


def atr_rel(h: np.ndarray, lo: np.ndarray, c: np.ndarray,
            period: int = ATR_PERIOD) -> np.ndarray:
    """ATR de Wilder relativo al cierre. El rango verdadero usa el cierre ANTERIOR."""
    n = len(c)
    out = np.full(n, np.nan)
    if n <= period:
        return out
    prev = np.concatenate(([np.nan], c[:-1]))
    tr = np.maximum(h - lo, np.maximum(np.abs(h - prev), np.abs(lo - prev)))
    tr[0] = h[0] - lo[0]
    atr = np.full(n, np.nan)
    atr[period] = float(np.mean(tr[1:period + 1]))      # primer valor: media simple de Wilder
    for j in range(period + 1, n):
        atr[j] = (atr[j - 1] * (period - 1) + tr[j]) / period
    good = (c > 0) & np.isfinite(atr)
    out[good] = atr[good] / c[good]
    return out


def close_to_close(c: np.ndarray, n: int) -> np.ndarray:
    """σ por vela de los log-retornos de cierre en una ventana de `n` velas."""
    r = np.concatenate(([np.nan], _safe_log(c[1:], c[:-1])))
    m = _roll_mean(r, n)
    m2 = _roll_mean(r**2, n)
    var = m2 - m**2
    return np.sqrt(np.maximum(var, 0.0)) * np.sqrt(n / max(n - 1, 1))


def parkinson(h: np.ndarray, lo: np.ndarray, n: int) -> np.ndarray:
    """Parkinson (1980): σ² = media(ln(máx/mín)²) / (4·ln 2)."""
    hl = _safe_log(h, lo)
    return np.sqrt(np.maximum(_roll_mean(hl**2, n) / (4.0 * np.log(2.0)), 0.0))


def garman_klass(o: np.ndarray, h: np.ndarray, lo: np.ndarray, c: np.ndarray,
                 n: int) -> np.ndarray:
    """Garman y Klass (1980): 0,5·ln(máx/mín)² − (2·ln2 − 1)·ln(cierre/apertura)²."""
    hl, co = _safe_log(h, lo), _safe_log(c, o)
    term = 0.5 * hl**2 - (2.0 * np.log(2.0) - 1.0) * co**2
    return np.sqrt(np.maximum(_roll_mean(term, n), 0.0))


def rogers_satchell(o: np.ndarray, h: np.ndarray, lo: np.ndarray, c: np.ndarray,
                    n: int) -> np.ndarray:
    """Rogers y Satchell (1991): insensible a la deriva de la vela."""
    hc, ho = _safe_log(h, c), _safe_log(h, o)
    lc, lo_o = _safe_log(lo, c), _safe_log(lo, o)
    return np.sqrt(np.maximum(_roll_mean(hc * ho + lc * lo_o, n), 0.0))


def yang_zhang(o: np.ndarray, h: np.ndarray, lo: np.ndarray, c: np.ndarray,
               n: int) -> np.ndarray:
    """Yang y Zhang (2000): apertura + cierre + Rogers–Satchell, insesgado con saltos.

    σ² = σ_o² + k·σ_c² + (1 − k)·σ_rs², con σ_o el salto de apertura (ln(apertura/cierre previo))
    y σ_c el movimiento dentro de la vela (ln(cierre/apertura)).
    """
    if n <= MIN_WINDOW:
        return np.full(len(c), np.nan)
    prev_c = np.concatenate(([np.nan], c[:-1]))
    jump = _safe_log(o, prev_c)                       # salto de apertura
    body = _safe_log(c, o)                            # cuerpo de la vela
    v_o = _roll_mean(jump**2, n) - _roll_mean(jump, n) ** 2
    v_c = _roll_mean(body**2, n) - _roll_mean(body, n) ** 2
    v_rs = rogers_satchell(o, h, lo, c, n) ** 2
    k = YZ_K_NUM / (YZ_K_DEN + (n + 1) / (n - 1))
    var = np.maximum(v_o, 0.0) + k * np.maximum(v_c, 0.0) + (1.0 - k) * v_rs
    return np.sqrt(np.maximum(var, 0.0))


# Estimadores que solo necesitan el camino, por nombre pre-registrado.
OHLC = {
    "atr14": lambda o, h, lo, c, n: atr_rel(h, lo, c, ATR_PERIOD),
    "close_to_close": lambda o, h, lo, c, n: close_to_close(c, n),
    "parkinson": lambda o, h, lo, c, n: parkinson(h, lo, n),
    "garman_klass": lambda o, h, lo, c, n: garman_klass(o, h, lo, c, n),
    "yang_zhang": lambda o, h, lo, c, n: yang_zhang(o, h, lo, c, n),
    "rogers_satchell": lambda o, h, lo, c, n: rogers_satchell(o, h, lo, c, n),
}


def of(name: str, o: np.ndarray, h: np.ndarray, lo: np.ndarray, c: np.ndarray,
       window: int) -> np.ndarray:
    """σ relativo por vela del estimador `name` (los de `OHLC`). Falla si no existe."""
    fn = OHLC.get(name)
    if fn is None:
        raise ValueError(f"estimador de volatilidad desconocido: {name!r}; "
                         f"disponibles: {sorted(OHLC)} (HAR-RV vive en `harrv.py`)")
    return fn(o, h, lo, c, window)
