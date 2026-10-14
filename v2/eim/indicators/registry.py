"""Registro de indicadores del catálogo (`CATALOG.md`): id → función, familia, entradas, defaults.

`compute(id, data)` normaliza la salida a `dict[str, ndarray]` para usarlo de forma uniforme
(agente `technical` de T35, tests de truncado). `candle_arrays` convierte velas en arreglos.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from eim.core import Candle
from eim.indicators import flow, momentum, trend, volatility, volume


@dataclass(frozen=True)
class IndicatorSpec:
    id: str
    family: str  # tendencia | momentum | volatilidad | volumen | flujo
    fn: Callable
    inputs: tuple[str, ...]
    defaults: dict = field(default_factory=dict)
    source: str = "velas"  # de dónde salen las entradas


_HLC = ("high", "low", "close")
_TAKER = ("volume", "taker_buy_v")
_SPECS = [
    IndicatorSpec("MA", "tendencia", trend.ma, ("close",), {"periods": (7, 25, 99)}),
    IndicatorSpec("EMA", "tendencia", trend.ema_lines, ("close",), {"periods": (7, 25, 99)}),
    IndicatorSpec("WMA", "tendencia", trend.wma_lines, ("close",), {"periods": (7, 25, 99)}),
    IndicatorSpec("SAR", "tendencia", trend.sar, ("high", "low"),
                  {"start": 0.02, "step": 0.02, "maximum": 0.2}),
    IndicatorSpec("SUPER", "tendencia", trend.supertrend, _HLC, {"n": 10, "k": 3.0}),
    IndicatorSpec("DMI", "tendencia", trend.dmi, _HLC, {"n": 14, "m": 6}),
    IndicatorSpec("MACD", "momentum", momentum.macd, ("close",),
                  {"fast": 12, "slow": 26, "signal": 9}),
    IndicatorSpec("RSI", "momentum", momentum.rsi_lines, ("close",), {"periods": (6, 12, 24)}),
    IndicatorSpec("KDJ", "momentum", momentum.kdj, _HLC, {"n": 9, "m1": 3, "m2": 3}),
    IndicatorSpec("StochRSI", "momentum", momentum.stochrsi, ("close",),
                  {"n_rsi": 14, "n_stoch": 14, "k": 3, "d": 3}),
    IndicatorSpec("WR", "momentum", momentum.wr, _HLC, {"n": 14}),
    IndicatorSpec("CCI", "momentum", momentum.cci, _HLC, {"n": 14}),
    IndicatorSpec("MTM", "momentum", momentum.mtm, ("close",), {"n": 12, "m": 6}),
    IndicatorSpec("TRIX", "momentum", momentum.trix, ("close",), {"n": 12, "m": 9}),
    IndicatorSpec("BOLL", "volatilidad", volatility.boll, ("close",), {"n": 20, "k": 2.0}),
    IndicatorSpec("ATR", "volatilidad", volatility.atr, _HLC, {"n": 14}),
    IndicatorSpec("VOL", "volumen", volume.vol, ("volume",), {"periods": (5, 10)}),
    IndicatorSpec("OBV", "volumen", volume.obv, ("close", "volume"), {"m": 30}),
    IndicatorSpec("MFI", "volumen", volume.mfi, (*_HLC, "volume"), {"n": 14}),
    IndicatorSpec("EMV", "volumen", volume.emv, ("high", "low", "volume"), {"n": 14, "m": 9}),
    IndicatorSpec("VWAP", "volumen", volume.vwap, (*_HLC, "volume", "t"),
                  {"period_ms": volume.DAY_MS}),
    IndicatorSpec("AVL", "volumen", volume.avl, (*_HLC, "volume")),
    IndicatorSpec("BS.Vol", "flujo", flow.taker_volume, _TAKER, source="velas: taker_buy_v"),
    IndicatorSpec("TakerRatio", "flujo", flow.taker_ratio, _TAKER, {"n": 1},
                  source="velas: taker_buy_v"),
    IndicatorSpec("Delta", "flujo", flow.delta, _TAKER, source="velas: taker_buy_v"),
    IndicatorSpec("CVD", "flujo", flow.cvd, _TAKER, source="velas: taker_buy_v"),
    IndicatorSpec("TradeSize", "flujo", flow.avg_trade_size, ("volume", "trades"), {"n": 20},
                  source="velas: trades"),
    IndicatorSpec("Basis", "flujo", flow.basis, ("close", "index"),
                  source="cierre perpetuo + klines de índice (indexPriceKlines)"),
]
SPECS: dict[str, IndicatorSpec] = {s.id: s for s in _SPECS}


def compute(indicator_id: str, data: Mapping[str, Sequence[float] | np.ndarray],
            **params) -> dict[str, np.ndarray]:
    """Calcula un indicador del registro. Salida: líneas con nombre (una sola → {id: arr})."""
    spec = SPECS[indicator_id]
    missing = [k for k in spec.inputs if k not in data]
    if missing:
        raise KeyError(f"{indicator_id}: faltan entradas {missing}")
    out = spec.fn(*(data[k] for k in spec.inputs), **{**spec.defaults, **params})
    return out if isinstance(out, dict) else {indicator_id.lower(): out}


def candle_arrays(candles: Sequence[Candle]) -> dict[str, np.ndarray]:
    """Velas → arreglos `t, open, high, low, close, volume, taker_buy_v, trades` (None → NaN)."""
    def col(get) -> np.ndarray:
        return np.array([np.nan if (x := get(c)) is None else x for c in candles], dtype=float)

    return {
        "t": np.array([c.t for c in candles], dtype=np.int64),
        "open": col(lambda c: c.o), "high": col(lambda c: c.h), "low": col(lambda c: c.l),
        "close": col(lambda c: c.c), "volume": col(lambda c: c.v),
        "taker_buy_v": col(lambda c: c.taker_buy_v), "trades": col(lambda c: c.trades),
    }
