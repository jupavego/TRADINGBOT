"""Variables del flujo de operaciones (T80): desequilibrio, intensidad y VPIN. Puras.

El agresor es quien cruza el spread: `buy_v` es volumen comprado a mercado y `sell_v` vendido a
mercado (el `maker` de `aggTrade` ya se traduce en la captura). Todas las ventanas miran hacia
atrás; el VPIN se calcula sobre cubos de volumen CERRADOS, así que una fila nunca usa el cubo que
aún se está llenando.
"""

from __future__ import annotations

import numpy as np

from eim.hft.features.sampling import bucket_last_rows, trailing_sum, volume_clock


def trade_imbalance(buy_v: np.ndarray, sell_v: np.ndarray, window: int,
                    eps: float = 1e-12) -> np.ndarray:
    """Desequilibrio del flujo agresor de la ventana, en [−1, 1]."""
    b, s = trailing_sum(buy_v, window), trailing_sum(sell_v, window)
    tot = b + s
    return np.where(tot > eps, (b - s) / np.maximum(tot, eps), 0.0)


def arrival_intensity(n_trades: np.ndarray, window: int, ref: int,
                      eps: float = 1e-9) -> np.ndarray:
    """Intensidad de llegadas: operaciones por cubo de la ventana corta frente a la larga.

    1 = ritmo normal; > 1 = ráfaga. Sin historia para la referencia devuelve NaN.
    """
    short = trailing_sum(n_trades, window) / window
    long = trailing_sum(n_trades, ref) / ref
    return short / np.maximum(long, eps)


def vpin(buy_v: np.ndarray, sell_v: np.ndarray, bucket: float, n_buckets: int,
         eps: float = 1e-12) -> np.ndarray:
    """VPIN por cubos de volumen: media de |compra − venta| / volumen de los `n_buckets`
    últimos cubos cerrados. Cada fila recibe el último valor disponible en su instante; NaN
    mientras no hay `n_buckets` cubos cerrados."""
    b, s = np.asarray(buy_v, float), np.asarray(sell_v, float)
    out = np.full(b.shape[0], np.nan)
    if b.shape[0] == 0:
        return out
    idx = volume_clock(b + s, bucket)
    last = bucket_last_rows(idx)
    if last.size < n_buckets:
        return out
    starts = np.concatenate([[0], last[:-1] + 1])
    bb = np.add.reduceat(b, starts)
    ss = np.add.reduceat(s, starts)
    num = trailing_sum(np.abs(bb - ss), n_buckets)
    den = trailing_sum(bb + ss, n_buckets)
    val = np.where(den > eps, num / np.maximum(den, eps), np.nan)
    out[last] = val
    # cada fila hereda el valor del último cubo cerrado (nunca el que se está llenando)
    pos = np.full(b.shape[0], -1)
    pos[last] = np.arange(last.size)
    pos = np.maximum.accumulate(pos)
    ok = pos >= 0
    out[ok] = val[pos[ok]]
    return out
