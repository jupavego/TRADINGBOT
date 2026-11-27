"""Variables del libro (T80): microprecio, OFI multinivel, profundidad y spread. Puras.

Sin red, sin disco y sin estado global: todo entra como arreglos de numpy y sale como arreglos.
Cada fila es un cubo de muestreo del panel y su estado del libro es el del CIERRE del cubo, así
que una variable solo puede mirar su fila y las anteriores (ver `sampling.trailing_sum`).

El OFI por evento reutiliza `_ofi_step` de `eim/data/micro.py` (T23), aplicado nivel a nivel: es
el OFI multinivel de Cont-Kukanov-Stoikov extendido a los 5 primeros niveles. Los niveles que el
libro no tiene se rellenan con precio y cantidad 0, que aportan 0 al evento.
"""

from __future__ import annotations

import numpy as np

from eim.data.micro import _ofi_step

Levels = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]


def mid(bid_p: np.ndarray, ask_p: np.ndarray) -> np.ndarray:
    """Precio medio del mejor nivel."""
    return (np.asarray(bid_p, float) + np.asarray(ask_p, float)) / 2


def microprice(bid_p: np.ndarray, bid_q: np.ndarray, ask_p: np.ndarray,
               ask_q: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Microprecio ponderado por el tamaño contrario: (bid·askQ + ask·bidQ) / (bidQ + askQ).

    Es el mid desplazado hacia el lado con menos cola; con colas iguales coincide con el mid.
    """
    bp, bq = np.asarray(bid_p, float), np.asarray(bid_q, float)
    ap, aq = np.asarray(ask_p, float), np.asarray(ask_q, float)
    w = bq + aq
    return np.where(w > eps, (bp * aq + ap * bq) / np.maximum(w, eps), (bp + ap) / 2)


def tilt_bps(bid_p: np.ndarray, bid_q: np.ndarray, ask_p: np.ndarray,
             ask_q: np.ndarray) -> np.ndarray:
    """Desvío del microprecio frente al mid, en pb: la señal del microprecio."""
    m = mid(bid_p, ask_p)
    return (microprice(bid_p, bid_q, ask_p, ask_q) - m) / np.maximum(m, 1e-12) * 1e4


def relative_spread_bps(bid_p: np.ndarray, ask_p: np.ndarray) -> np.ndarray:
    """Spread del mejor nivel en pb del mid."""
    bp, ap = np.asarray(bid_p, float), np.asarray(ask_p, float)
    return (ap - bp) / np.maximum((ap + bp) / 2, 1e-12) * 1e4


def depth_imbalance(bid_q: np.ndarray, ask_q: np.ndarray, levels: int = 5,
                    eps: float = 1e-12) -> np.ndarray:
    """Desequilibrio de profundidad acumulada de los `levels` primeros niveles, en [−1, 1]."""
    b = np.asarray(bid_q, float)[:, :levels].sum(axis=1)
    a = np.asarray(ask_q, float)[:, :levels].sum(axis=1)
    return np.where(b + a > eps, (b - a) / np.maximum(b + a, eps), 0.0)


def ofi_event(prev: tuple[float, ...] | np.ndarray, cur: tuple[float, ...] | np.ndarray,
              levels: int) -> np.ndarray:
    """OFI de un evento del libro, nivel a nivel. `prev`/`cur` = (bp, bq, ap, aq) concatenados
    por nivel: arreglos de longitud ≥ `levels` en el orden del libro (mejor primero)."""
    p, c = np.asarray(prev, float), np.asarray(cur, float)
    out = np.empty(levels)
    for k in range(levels):
        out[k] = _ofi_step((p[0][k], p[1][k], p[2][k], p[3][k]),
                           (c[0][k], c[1][k], c[2][k], c[3][k]))
    return out


def ofi_scaled(ofi: np.ndarray, bid_q: np.ndarray, ask_q: np.ndarray,
               eps: float = 1e-12) -> np.ndarray:
    """OFI acumulado dividido por la profundidad media del nivel: adimensional y comparable.

    `ofi` y las cantidades son (n, niveles). La escala usa la profundidad del cierre del cubo
    (información del propio cubo, nunca posterior).
    """
    o = np.asarray(ofi, float)
    scale = (np.asarray(bid_q, float)[:, :o.shape[1]]
             + np.asarray(ask_q, float)[:, :o.shape[1]]) / 2
    return o / np.maximum(scale, eps)


def pad_levels(bp: list[float], bq: list[float], ap: list[float], aq: list[float],
               levels: int) -> Levels:
    """Los `levels` primeros niveles de cada lado, rellenando con 0 lo que el libro no tiene."""
    out = []
    for xs in (bp, bq, ap, aq):
        a = np.zeros(levels)
        n = min(levels, len(xs))
        if n:
            a[:n] = xs[:n]
        out.append(a)
    return out[0], out[1], out[2], out[3]
