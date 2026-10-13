"""Cálculo VWAP (puro). Misma lógica y columnas que F7/eim_vwap.py (regresión contra golden)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from eim.agents.vwap.params import PERIODS, PREFIX, VWAPParams


def _month_start(ts: pd.Series) -> pd.Series:
    return ts.dt.normalize() - pd.to_timedelta(ts.dt.day - 1, unit="D")


def period_keys(ts: pd.Series) -> dict[str, pd.Series]:
    """Inicio de período por vela: día UTC, lunes, quincena (días 1/16) y mes."""
    day = ts.dt.floor("D")
    ms = _month_start(ts)
    return {
        "daily": day,
        "weekly": day - pd.to_timedelta(ts.dt.dayofweek, unit="D"),
        "quincenal": ms.where(ts.dt.day <= 15, ms + pd.to_timedelta(15, unit="D")),
        "monthly": ms,
    }


def _typical(df: pd.DataFrame) -> pd.Series:
    return (df["high"] + df["low"] + df["close"]) / 3


def _period_vwap(df: pd.DataFrame, key: pd.Series, prefix: str) -> None:
    tp, vol = _typical(df), df["volume"]
    cum_vol = vol.groupby(key).cumsum()
    vwap = (tp * vol).groupby(key).cumsum() / cum_vol
    std = np.sqrt((vol * (tp - vwap) ** 2).groupby(key).cumsum() / cum_vol)
    df[prefix] = vwap
    df[f"{prefix}_STD"] = std
    df[f"{prefix}_UPPER_1"] = vwap + std
    df[f"{prefix}_LOWER_1"] = vwap - std
    df[f"{prefix}_UPPER_2"] = vwap + 2 * std
    df[f"{prefix}_LOWER_2"] = vwap - 2 * std


def classify_position(close: pd.Series, vwap: pd.Series, std: pd.Series) -> pd.Series:
    """Posición del cierre respecto al VWAP en desviaciones estándar."""
    dev = (close - vwap) / std
    out = np.select(
        [dev > 2, dev > 1, dev > 0, dev > -1, dev > -2],
        ["EXTREMO_SOBRE", "ESTIRADO_SOBRE", "SOBRE_VWAP", "BAJO_VWAP", "ESTIRADO_BAJO"],
        default="EXTREMO_BAJO",
    )
    invalid = vwap.isna() | std.isna() | (std == 0)
    return pd.Series(np.where(invalid, "SIN_DATOS", out), index=close.index)


def compute_vwap(ohlcv: pd.DataFrame, periods: tuple[str, ...] = PERIODS) -> pd.DataFrame:
    """VWAP anclado + por período, con bandas, posición y pendiente (columnas del legado)."""
    df = ohlcv.copy().reset_index(drop=True)
    tp, vol = _typical(df), df["volume"]
    cum_vol = vol.cumsum()
    vwap = (tp * vol).cumsum() / cum_vol
    std = np.sqrt((vol * (tp - vwap) ** 2).cumsum() / cum_vol)
    df["VWAP_ANCHOR"], df["VWAP_ANCHOR_STD"] = vwap, std
    df["VWAP_ANCHOR_UPPER_1"], df["VWAP_ANCHOR_LOWER_1"] = vwap + std, vwap - std

    keys = period_keys(df["timestamp"])
    for period in periods:
        pre = PREFIX[period]
        df[f"{pre}_PERIOD"] = keys[period]
        _period_vwap(df, keys[period], pre)
        df[f"{pre}_POSITION"] = classify_position(df["close"], df[pre], df[f"{pre}_STD"])
        df[f"{pre}_SLOPE"] = (df[pre] - df[pre].shift(1)) / df[pre].shift(1) * 100
    return df


def interpret(position: str, slope: float | None, p: VWAPParams) -> float:
    """Probabilidad heurística de subida (%) según posición y pendiente. NO validada."""
    from eim.agents.vwap.params import POSITION_BIAS

    s = 0.0 if slope is None or np.isnan(slope) else float(slope)
    slope_bias = max(-p.slope_cap, min(p.slope_cap, s * p.slope_gain))
    return max(p.prob_floor, min(p.prob_cap, 50 + POSITION_BIAS.get(position, 0) + slope_bias))
