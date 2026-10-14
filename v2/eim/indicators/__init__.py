"""Biblioteca de indicadores técnicos (T34): funciones puras sobre arreglos numpy.

Catálogo y estado de cada indicador en `CATALOG.md`; convenciones en `_core.py`.
Binance no sirve indicadores calculados: todo se calcula localmente desde sus velas.
"""

from eim.indicators._core import ema, rma, rolling_max, rolling_min, rolling_std, sma, wma
from eim.indicators.registry import SPECS, IndicatorSpec, candle_arrays, compute
from eim.indicators.volatility import atr, true_range

__all__ = [
    "SPECS", "IndicatorSpec", "atr", "candle_arrays", "compute", "ema", "rma", "rolling_max",
    "rolling_min", "rolling_std", "sma", "true_range", "wma",
]
