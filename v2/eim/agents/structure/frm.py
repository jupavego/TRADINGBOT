"""FRM (EIM-FRM-001 v1.0.0): fórmulas F-001…F-022 sobre un DataFrame OHLCV. Puro, sin I/O.

Migrado de F7/eim_frm.py; mismo orden de cálculo y mismas columnas (regresión contra golden).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from eim.agents.structure.params import FRMParams

SPANS = (9, 21, 55, 100, 200)
_EMA = [f"EMA_{n}" for n in SPANS]


def _stack(df: pd.DataFrame) -> np.ndarray:
    """Pares alcistas consecutivos del stack (0–4)."""
    e = df[_EMA].to_numpy(float)
    return (e[:, :-1] > e[:, 1:]).sum(axis=1)


def _persistence(close: pd.Series, ema21: pd.Series) -> list[int]:
    above = (close > ema21).to_numpy()
    out = [0] * len(close)
    for i in range(1, len(out)):
        out[i] = max(out[i - 1], 0) + 1 if above[i] else min(out[i - 1], 0) - 1
    return out


def _bounces(close: np.ndarray, ema: np.ndarray, window: int) -> list[int]:
    """F-020: rebote = EMA tocada en la vela k y cierre del mismo lado que 2 velas atrás."""
    n = len(close)
    flag = np.zeros(n, dtype=int)
    if n > 2:
        lo = np.minimum(close[2:], close[1:-1])
        hi = np.maximum(close[2:], close[1:-1])
        touched = (lo <= ema[2:]) & (ema[2:] <= hi)
        now = np.sign(close[2:] - ema[2:])
        prev = np.sign(close[:-2] - ema[:-2])
        flag[2:] = (touched & (now == prev) & (now != 0)).astype(int)
    cum = np.concatenate([[0], np.cumsum(flag)])
    counts = [0] * n
    for i in range(2, n):
        start = max(2, i - window + 1)
        counts[i] = int(cum[i + 1] - cum[start])
    return counts


def _atr_relative(df: pd.DataFrame, period: int) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(period).mean() / df["close"] * 100


def compute_frm(ohlcv: pd.DataFrame, p: FRMParams | None = None) -> pd.DataFrame:
    """Pipeline FRM completo (Apéndice A). `ohlcv`: timestamp, open, high, low, close, volume."""
    p = p or FRMParams()
    df = ohlcv.copy().reset_index(drop=True)
    close = df["close"]

    for n in SPANS:  # F-001
        df[f"EMA_{n}"] = close.ewm(span=n, adjust=False).mean()

    pairs = _stack(df)  # F-002 / F-003
    names = {4: "BULL_PERFECT", 3: "BULL_PARTIAL", 2: "NEUTRAL",
             1: "BEAR_PARTIAL", 0: "BEAR_PERFECT"}
    df["STACK_ORDER"] = [names[int(k)] for k in pairs]
    df["STACK_SCORE"] = pairs * 2.5
    df["PRICE_VS_STACK"] = (close.to_numpy()[:, None] > df[_EMA].to_numpy(float)).sum(axis=1)

    for n in SPANS:  # F-005
        e = df[f"EMA_{n}"]
        df[f"SLOPE_{n}"] = (e - e.shift(1)) / e.shift(1) * 100
    for fast, slow in [(9, 21), (21, 55), (55, 100), (100, 200)]:  # F-006
        fe, se = df[f"EMA_{fast}"], df[f"EMA_{slow}"]
        df[f"SPREAD_{fast}_{slow}"] = (fe - se) / se * 100
    df["ELASTICITY"] = (close - df["EMA_200"]) / df["EMA_200"] * 100  # F-007
    avg = df["volume"].shift(1).rolling(p.volume_window).mean()
    df["VOLUME_RATIO"] = df["volume"] / avg  # F-008

    s9, s55 = df["SLOPE_9"], df["SLOPE_55"]  # F-009
    df["SLOPE_DIRECTION"] = np.select(
        [(s9 > 0) & (s55 > 0), (s9 < 0) & (s55 < 0)], ["UP", "DOWN"], default="NEUTRAL"
    )

    df["COMPRESSION_INDEX"] = (  # F-010
        df["SPREAD_9_21"].abs() + df["SPREAD_21_55"].abs()
        + df["SPREAD_55_100"].abs() + df["SPREAD_100_200"].abs()
    ) / 4
    for n in (9, 55):  # F-015
        df[f"CURVATURE_{n}"] = df[f"SLOPE_{n}"] - df[f"SLOPE_{n}"].shift(1)
    df["PERSISTENCE_ABOVE_21"] = _persistence(close, df["EMA_21"])  # F-016
    cl = close.to_numpy(float)
    for n in (9, 21, 55, 200):
        df[f"BOUNCE_COUNT_{n}"] = _bounces(cl, df[f"EMA_{n}"].to_numpy(float), p.bounce_window)

    for fast, slow in [(9, 21), (21, 55), (55, 200)]:  # F-021
        fn, sn = df[f"EMA_{fast}"], df[f"EMA_{slow}"]
        fp, sp = fn.shift(1), sn.shift(1)
        bull = (fp <= sp) & (fn > sn)
        bear = (fp >= sp) & (fn < sn)
        occurred = bull | bear
        direction = pd.Series("NONE", index=df.index)
        direction[bull] = "GOLDEN_CROSS" if (fast, slow) == (55, 200) else "BULLISH"
        direction[bear] = "DEATH_CROSS" if (fast, slow) == (55, 200) else "BEARISH"
        pre = f"CROSS_{fast}_{slow}"
        df[f"{pre}_occurred"] = occurred
        df[f"{pre}_direction"] = direction
        df[f"{pre}_magnitude"] = ((fn - sn).abs() / sn * 100).where(occurred, 0.0)

    df["ATR_RELATIVE"] = _atr_relative(df, p.atr_period)  # F-022
    ci = df["COMPRESSION_INDEX"]
    df["SPREAD_VELOCITY"] = ci - ci.shift(1)  # F-013

    below = (ci <= p.theta_compress).to_numpy()  # F-017
    dur = [0] * len(df)
    for i in range(1, len(df)):
        dur[i] = dur[i - 1] + 1 if below[i] else 0
    df["COMPRESSION_DURATION"] = dur

    sd = df["SLOPE_DIRECTION"].to_numpy()  # F-018
    signs = np.sign(df[[f"SLOPE_{n}" for n in SPANS]].to_numpy(float))
    want = np.where(sd == "UP", 1.0, -1.0)
    sync = (signs == want[:, None]).sum(axis=1) / 5 * 100
    df["SLOPE_SYNC"] = np.where(sd == "NEUTRAL", 0.0, sync)

    df["SPREAD_ACCELERATION"] = df["SPREAD_VELOCITY"] - df["SPREAD_VELOCITY"].shift(1)  # F-014

    w = p.coherence_weights  # F-011
    c = (
        w[0] * df["STACK_SCORE"] + w[1] * df["PRICE_VS_STACK"] * 2 + w[2] * df["SLOPE_SYNC"] / 10
        + w[3] * df["VOLUME_RATIO"].clip(0, 3) * (10 / 3) + w[4] * df["BOUNCE_COUNT_55"].clip(0, 10)
    )
    df["COHERENCE_SCORE"] = c.clip(0, 10)

    f = p.friction_weights  # F-012
    fr = (
        f[0] * (10 - (ci * 10).clip(0, 10)) + f[1] * (10 - df["ELASTICITY"].abs().clip(0, 10))
        + f[2] * (10 - df["VOLUME_RATIO"].clip(0, 3) * (10 / 3))
        + f[3] * (df["COMPRESSION_DURATION"] / 5).clip(0, 10)
        + f[4] * (10 - (df["ATR_RELATIVE"] * 10).clip(0, 10))
    )
    df["FRICTION_INDEX"] = fr.clip(0, 10)
    return df
