"""Price action (puro). Misma lógica que F7/eim_price_action.py (regresión contra golden)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_swings(df: pd.DataFrame, n: int) -> None:
    high, low = df["high"], df["low"]
    sh, sl = [False] * len(df), [False] * len(df)
    for i in range(n, len(df) - n):
        hw, lw = high.iloc[i - n:i + n + 1], low.iloc[i - n:i + n + 1]
        if high.iloc[i] == hw.max() and (hw == high.iloc[i]).sum() == 1:
            sh[i] = True
        if low.iloc[i] == lw.min() and (lw == low.iloc[i]).sum() == 1:
            sl[i] = True
    df["SWING_HIGH"], df["SWING_LOW"] = sh, sl


def compute_candle_patterns(df: pd.DataFrame) -> None:
    o, h, lo, c = df["open"], df["high"], df["low"], df["close"]
    body = (c - o).abs()
    rng = (h - lo).replace(0, np.nan)
    upper = h - pd.concat([c, o], axis=1).max(axis=1)
    lower = pd.concat([c, o], axis=1).min(axis=1) - lo
    o_p, c_p, h_p, l_p = o.shift(1), c.shift(1), h.shift(1), lo.shift(1)
    bull_now, bear_now = c > o, c < o
    bull_prev, bear_prev = c_p < o_p, c_p > o_p
    df["BULLISH_ENGULFING"] = (bull_now & bear_prev & (o <= c_p) & (c >= o_p)).fillna(False)
    df["BEARISH_ENGULFING"] = (bear_now & bull_prev & (o >= c_p) & (c <= o_p)).fillna(False)
    body_floor = body.where(body != 0, rng * 0.05)
    df["HAMMER"] = ((lower >= 2 * body) & (upper <= 0.3 * body_floor)).fillna(False)
    df["SHOOTING_STAR"] = ((upper >= 2 * body) & (lower <= 0.3 * body_floor)).fillna(False)
    df["DOJI"] = (body <= 0.1 * rng).fillna(False)
    df["INSIDE_BAR"] = ((h <= h_p) & (lo >= l_p)).fillna(False)
    df["OUTSIDE_BAR"] = ((h >= h_p) & (lo <= l_p)).fillna(False)


def compute_structure(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """HH/HL/LH/LL + BOS/CHOCH. Devuelve las últimas etiquetas de swing alto y bajo."""
    n = len(df)
    event, st = ["NONE"] * n, ["UNDEFINED"] * n
    lhp = llp = None
    lhl = lll = None
    broken_h = broken_l = True
    state = "UNDEFINED"
    close, high, low = df["close"], df["high"], df["low"]
    is_sh, is_sl = df["SWING_HIGH"], df["SWING_LOW"]
    for i in range(n):
        if lhp is not None and not broken_h and close.iloc[i] > lhp:
            event[i] = "BOS_ALCISTA" if state == "BULLISH" else "CHOCH_ALCISTA"
            broken_h, state = True, "BULLISH"
        if llp is not None and not broken_l and close.iloc[i] < llp:
            if event[i] == "NONE":
                event[i] = "BOS_BAJISTA" if state == "BEARISH" else "CHOCH_BAJISTA"
            broken_l, state = True, "BEARISH"
        if is_sh.iloc[i]:
            lhl = "HH" if (lhp is None or high.iloc[i] > lhp) else "LH"
            lhp, broken_h = high.iloc[i], False
        if is_sl.iloc[i]:
            lll = "HL" if (llp is None or low.iloc[i] > llp) else "LL"
            llp, broken_l = low.iloc[i], False
        st[i] = state
    df["STRUCTURE_EVENT"], df["STRUCTURE_STATE"] = event, st
    return lhl, lll


def compute_sr_zones(df: pd.DataFrame, tolerance_pct: float) -> list[dict]:
    pts = sorted(list(df.loc[df["SWING_HIGH"], "high"]) + list(df.loc[df["SWING_LOW"], "low"]))
    zones: list[dict] = []
    for p in pts:
        for z in zones:
            if z["price"] == 0:
                continue
            if abs(p - z["price"]) / z["price"] * 100 <= tolerance_pct:
                z["touches"] += 1
                z["price"] += (p - z["price"]) / z["touches"]
                break
        else:
            zones.append({"price": float(p), "touches": 1})
    zones.sort(key=lambda z: z["price"])
    return zones


def compute_price_action(
    ohlcv: pd.DataFrame, fractal_n: int = 2, tolerance_pct: float = 0.5
) -> tuple[pd.DataFrame, list[dict], tuple[str | None, str | None]]:
    """Devuelve (frame, zonas S/R, (última etiqueta swing alto, bajo))."""
    df = ohlcv.copy().reset_index(drop=True)
    compute_swings(df, fractal_n)
    compute_candle_patterns(df)
    labels = compute_structure(df)
    return df, compute_sr_zones(df, tolerance_pct), labels
