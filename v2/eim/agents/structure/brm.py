"""BRM (EIM-BRM-001 v1.0.1): reglas R-001…R-003, combinaciones y matriz de transiciones.

Migrado de F7/eim_brm_irm.py. Puro, sin I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from eim.agents.structure.params import BRMParams

_ALL = {"E-01_TREND_STRONG", "E-02_TREND_WEAK", "E-03_ORDERED", "E-04_EXHAUSTED",
        "E-05_COMPRESSED", "E-06_EXPANDING", "E-07_DIVERGENT"}

# Transiciones válidas (BRM-001 § Parte III); las demás se marcan INVALID.
VALID_TRANSITIONS: dict[str, set[str]] = {
    "E-01_TREND_STRONG": {"E-01_TREND_STRONG", "E-02_TREND_WEAK", "E-03_ORDERED",
                          "E-04_EXHAUSTED", "E-07_DIVERGENT"},
    "E-02_TREND_WEAK": set(_ALL),
    "E-03_ORDERED": set(_ALL),
    "E-04_EXHAUSTED": {"E-02_TREND_WEAK", "E-03_ORDERED", "E-04_EXHAUSTED",
                       "E-05_COMPRESSED", "E-07_DIVERGENT"},
    "E-05_COMPRESSED": {"E-05_COMPRESSED", "E-06_EXPANDING", "E-07_DIVERGENT"},
    "E-06_EXPANDING": {"E-01_TREND_STRONG", "E-02_TREND_WEAK", "E-03_ORDERED",
                       "E-06_EXPANDING", "E-07_DIVERGENT"},
    "E-07_DIVERGENT": set(_ALL),
}

IMPOSSIBLE = {("E-05_COMPRESSED", "HIGH_ENERGY"), ("E-06_EXPANDING", "COMPRESSED")}
UNUSUAL = {("E-01_TREND_STRONG", "COMPRESSED"), ("E-04_EXHAUSTED", "HIGH_ENERGY")}


def _nan(x) -> bool:
    return x is None or bool(pd.isna(x))


def structural_state(row: dict, t: BRMParams) -> str:
    """R-001: E-01…E-07 (jerarquía: compresión, expansión, fuerte, ordenado, agotado, débil)."""
    ci = row.get("COMPRESSION_INDEX", np.nan)
    cd = row.get("COMPRESSION_DURATION", 0)
    cd_prev = row.get("COMPRESSION_DURATION_PREV", 0)
    ci_prev = row.get("COMPRESSION_INDEX_PREV", np.nan)
    sv = row.get("SPREAD_VELOCITY", np.nan)
    so = row.get("STACK_ORDER", "NEUTRAL")
    ss = row.get("STACK_SCORE", 5.0)
    pvs = row.get("PRICE_VS_STACK", 2)
    sd = row.get("SLOPE_DIRECTION", "NEUTRAL")

    if not _nan(ci) and ci <= t.theta_001_compress and cd >= t.theta_006_duration:
        return "E-05_COMPRESSED"
    if not _nan(sv) and sv > t.theta_004_velocity and (
        cd_prev >= 3 or (not _nan(ci_prev) and ci_prev <= t.theta_001_compress * 1.5)
    ):
        return "E-06_EXPANDING"
    if so == "BULL_PERFECT" and ss >= 7.5 and pvs >= 4 and sd == "UP":
        return "E-01_TREND_STRONG"
    if so == "BEAR_PERFECT" and ss <= 2.5 and pvs <= 1 and sd == "DOWN":
        return "E-01_TREND_STRONG"
    if ss >= 5.0 and sd != "NEUTRAL":
        return "E-03_ORDERED"
    if so in ("BULL_PARTIAL", "BEAR_PARTIAL") and not _nan(sv) and sv < -t.theta_004_velocity:
        return "E-04_EXHAUSTED"
    if ss >= 2.5 and sd != "NEUTRAL":
        return "E-02_TREND_WEAK"
    return "E-07_DIVERGENT"


def momentum_state(row: dict, t: BRMParams) -> str:
    """R-002: REVERSING → ACCELERATING → DECELERATING → STABLE (C-008: dirección vs t-3)."""
    sd = row.get("SLOPE_DIRECTION", "NEUTRAL")
    sv = row.get("SPREAD_VELOCITY", np.nan)
    sa = row.get("SPREAD_ACCELERATION", np.nan)
    c9 = row.get("CURVATURE_9", np.nan)
    c55 = row.get("CURVATURE_55", np.nan)
    cross_any = (row.get("CROSS_9_21_occurred", False) or row.get("CROSS_21_55_occurred", False)
                 or row.get("CROSS_55_200_occurred", False))
    d = 1 if sd == "UP" else (-1 if sd == "DOWN" else 0)

    opposing = (d != 0 and not _nan(c55) and np.sign(c55) != d
                and abs(c55) > t.theta_005_curvature * 3)
    sd_t3 = row.get("SLOPE_DIRECTION_T3", "NEUTRAL")
    changed = sd != sd_t3 and sd_t3 != "NEUTRAL"
    if cross_any or opposing or changed:
        return "REVERSING"
    if (not _nan(sv) and sv > t.theta_004_velocity and not _nan(sa) and sa > 0 and d != 0
            and not _nan(c9) and np.sign(c9) == d and not _nan(c55) and np.sign(c55) == d):
        return "ACCELERATING"
    if not _nan(sv) and sv < -t.theta_004_velocity:
        return "DECELERATING"
    if not _nan(sa) and sa < 0 and not _nan(sv) and sv > 0:
        return "DECELERATING"
    if d != 0 and not _nan(c9) and np.sign(c9) != d and abs(c9) > t.theta_005_curvature:
        return "DECELERATING"
    return "STABLE"


def energy_state(row: dict, t: BRMParams) -> str:
    """R-003: COMPRESSED → HIGH_ENERGY → LOW_ENERGY → MODERATE_ENERGY."""
    ci = row.get("COMPRESSION_INDEX", np.nan)
    cd = row.get("COMPRESSION_DURATION", 0)
    el = row.get("ELASTICITY", np.nan)
    sv = row.get("SPREAD_VELOCITY", np.nan)
    ar = row.get("ATR_RELATIVE", np.nan)
    if not _nan(ci) and ci <= t.theta_001_compress and cd >= t.theta_006_duration:
        return "COMPRESSED"
    if (not _nan(ci) and ci > t.theta_002_expand and not _nan(el) and abs(el) > t.theta_003_elastic
            and not _nan(sv) and sv > t.theta_004_velocity and not _nan(ar) and ar > t.atr_high):
        return "HIGH_ENERGY"
    if (not _nan(ci) and ci <= t.theta_002_expand and cd < t.theta_006_duration
            and not _nan(el) and abs(el) <= t.theta_003_elastic / 2
            and not _nan(ar) and ar < t.atr_low):
        return "LOW_ENERGY"
    return "MODERATE_ENERGY"


def combination_status(structural: str, energy: str) -> str:
    if (structural, energy) in IMPOSSIBLE:
        return "IMPOSIBLE"
    if (structural, energy) in UNUSUAL:
        return "INUSUAL"
    return "NORMAL"


def transition_status(states: pd.Series) -> pd.Series:
    """Estado[t-1] → estado[t] contra VALID_TRANSITIONS; la primera vela es N/A."""
    prev = states.shift(1)
    out = [
        "N/A" if pd.isna(p) else ("VALID" if c in VALID_TRANSITIONS.get(p, set()) else "INVALID")
        for c, p in zip(states, prev, strict=True)
    ]
    return pd.Series(out, index=states.index)


def compute_brm(df: pd.DataFrame, t: BRMParams | None = None) -> pd.DataFrame:
    """Añade L3: STRUCTURAL/MOMENTUM/ENERGY_STATE, COMBINATION_STATUS, TRANSITION_STATUS."""
    t = t or BRMParams()
    df = df.copy()
    df["COMPRESSION_DURATION_PREV"] = df["COMPRESSION_DURATION"].shift(1).fillna(0)
    df["COMPRESSION_INDEX_PREV"] = df["COMPRESSION_INDEX"].shift(1)
    df["SLOPE_DIRECTION_T3"] = df["SLOPE_DIRECTION"].shift(3).fillna("NEUTRAL")
    rows = df.to_dict("records")
    df["STRUCTURAL_STATE"] = [structural_state(r, t) for r in rows]
    df["MOMENTUM_STATE"] = [momentum_state(r, t) for r in rows]
    df["ENERGY_STATE"] = [energy_state(r, t) for r in rows]
    df["COMBINATION_STATUS"] = [
        combination_status(s, e) for s, e in zip(df["STRUCTURAL_STATE"], df["ENERGY_STATE"],
                                                 strict=True)
    ]
    df["TRANSITION_STATUS"] = transition_status(df["STRUCTURAL_STATE"])
    return df
