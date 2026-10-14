"""Familia flujo: derivados de datos propios de Binance (taker buy/sell, trades, mark/index).

Requieren `Candle.taker_buy_v` / `Candle.trades` (klines de Binance, campos 9 y 8) o series
de precio índice/marca. Si la fuente no los entrega, el llamador debe pasar NaN: la salida
queda NaN (nunca se rellena con supuestos).
"""

from __future__ import annotations

import numpy as np

from eim.indicators._core import ArrayLike, arr, div, rolling_sum, sma


def taker_volume(volume: ArrayLike, taker_buy_v: ArrayLike) -> dict[str, np.ndarray]:
    """BS. Vol: volumen comprador agresor (buy) y vendedor agresor (sell = V − buy)."""
    v, b = arr(volume), arr(taker_buy_v)
    return {"buy": b, "sell": v - b}


def taker_ratio(volume: ArrayLike, taker_buy_v: ArrayLike, n: int = 1) -> np.ndarray:
    """Ratio comprador/vendedor sumado en n velas (buy/sell). Sin venta → NaN."""
    tv = taker_volume(volume, taker_buy_v)
    if n == 1:
        return div(tv["buy"], tv["sell"])
    return div(rolling_sum(tv["buy"], n), rolling_sum(tv["sell"], n))


def delta(volume: ArrayLike, taker_buy_v: ArrayLike) -> np.ndarray:
    """Delta de volumen por vela: buy − sell = 2·buy − V."""
    return 2 * arr(taker_buy_v) - arr(volume)


def cvd(volume: ArrayLike, taker_buy_v: ArrayLike) -> np.ndarray:
    """Delta acumulado desde el inicio de la serie (nivel relativo; un NaN no suma y queda NaN)."""
    d = delta(volume, taker_buy_v)
    hole = np.isnan(d)
    out = np.cumsum(np.where(hole, 0.0, d))
    out[hole] = np.nan
    return out


def avg_trade_size(volume: ArrayLike, trades: ArrayLike, n: int = 20) -> dict[str, np.ndarray]:
    """Tamaño medio por operación (V / trades) y su SMA(n). trades = 0 → NaN."""
    x = div(arr(volume), arr(trades))
    return {"size": x, "ma": sma(x, n)}


def basis(price: ArrayLike, index: ArrayLike) -> np.ndarray:
    """Basis relativo (%): (precio perpetuo o marca − índice) / índice · 100."""
    p, i = arr(price), arr(index)
    return 100 * div(p - i, i)
