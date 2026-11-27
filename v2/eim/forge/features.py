"""Variables de la forja (T208): todo lo que las recetas pueden mirar, calculado una sola vez.

Todas son **causales**: el valor en la vela `i` solo usa velas ≤ `i`, que es lo que una señal
evaluada al cierre de `i` puede saber. Las que se comparan con el futuro (Donchian, rango de
apertura, sesión anterior) van desplazadas o ancladas para que no incluyan la propia vela cuando no
deben. Una prueba del gate lo comprueba vela a vela (`tests/forge/test_causalidad.py`).

Las fuentes son las cinco familias del catálogo (`eim/indicators/CATALOG.md`) más lo propio del
intradía de sesión: VWAP de sesión, rango de apertura, sesión anterior, CVD de sesión y la hora.
"""

from __future__ import annotations

import numpy as np

from eim.forge import anchored
from eim.forge.data import Series
from eim.forge.session import Sessions
from eim.indicators import momentum, trend, volatility, volume
from eim.indicators._core import div, ema, rolling_max, rolling_min, rolling_std, shift, sma, wma

MA_PERIODS = (5, 9, 10, 20, 21, 50, 100)
DONCHIAN = (10, 20, 40)
OPEN_RANGE = (3, 6, 12)
Z_PERIODS = (20, 50, 100)
RSI_PERIODS = (7, 14, 21)
ROC_PERIODS = (6, 12, 24)
VOL_PERIODS = (20, 50)


def _streak(c: np.ndarray) -> np.ndarray:
    """Racha firmada de cierres en la misma dirección (+3 = tres cierres al alza seguidos)."""
    s = np.sign(np.diff(c, prepend=c[:1]))
    out = np.zeros(len(c))
    run = 0.0
    for i in range(1, len(c)):
        run = run + s[i] if s[i] != 0 and s[i] == s[i - 1] else s[i]
        out[i] = run
    return out


def _pct_rank(x: np.ndarray, n: int) -> np.ndarray:
    """Rango percentil de `x[i]` dentro de sus últimas `n` observaciones (0..1), causal."""
    from eim.indicators._core import windows

    w = windows(x, n)
    if w is None:
        return np.full(len(x), np.nan)
    r = (w <= x[n - 1:, None]).sum(axis=1) / n
    return np.r_[np.full(n - 1, np.nan), r]


def build(s: Series, ss: Sessions) -> dict[str, np.ndarray]:
    """Todas las variables de la forja, como arreglos de la longitud de la serie."""
    o, h, lo, c, v = s.o, s.h, s.l, s.c, s.v
    f: dict[str, np.ndarray] = {"o": o, "h": h, "l": lo, "c": c, "v": v}

    # --- tendencia -------------------------------------------------------------------------
    for n in MA_PERIODS:
        f[f"ema{n}"] = ema(c, n)
        f[f"sma{n}"] = sma(c, n)
        f[f"wma{n}"] = wma(c, n)
    for n in (20, 50):
        f[f"slope_ema{n}"] = f[f"ema{n}"] - shift(f[f"ema{n}"], 3)
    for n, k in ((10, 3.0), (20, 3.0)):
        f[f"st{n}_dir"] = trend.supertrend(h, lo, c, n, k)["dir"]
    f["sar_dir"] = np.sign(c - trend.sar(h, lo))
    d = trend.dmi(h, lo, c, 14)
    f["pdi14"], f["mdi14"], f["adx14"] = d["pdi"], d["mdi"], d["adx"]

    # --- volatilidad y régimen -------------------------------------------------------------
    for n in (7, 14, 20, 50):
        f[f"atr{n}"] = volatility.atr(h, lo, c, n)
    f["atr_ratio"] = div(f["atr7"], f["atr50"])
    for k in (2.0, 2.5):
        b = volatility.boll(c, 20, k)
        tag = str(k).replace(".", "")
        f[f"bb{tag}_up"], f[f"bb{tag}_dn"], f[f"bb{tag}_mb"] = b["up"], b["dn"], b["mb"]
    f["bb_width_pct"] = _pct_rank(div(f["bb20_up"] - f["bb20_dn"], f["bb20_mb"]), 200)
    f["kelt_up"] = f["ema20"] + 2 * f["atr20"]
    f["kelt_dn"] = f["ema20"] - 2 * f["atr20"]
    rng = h - lo
    f["range_rel"] = div(rng, sma(rng, 20))

    # --- ruptura de nivel ------------------------------------------------------------------
    for n in DONCHIAN:                       # desplazados: el máximo de las N velas ANTERIORES
        f[f"dc_hi{n}"] = shift(rolling_max(h, n), 1)
        f[f"dc_lo{n}"] = shift(rolling_min(lo, n), 1)
    for k in OPEN_RANGE:
        f[f"or_hi{k}"], f[f"or_lo{k}"] = anchored.opening_range(h, lo, ss, k)
    f["prev_hi"], f["prev_lo"] = anchored.previous_session(h, lo, ss)

    # --- reversión a la media --------------------------------------------------------------
    for n in Z_PERIODS:
        f[f"z_ema{n}"] = div(c - f[f"ema{n}"] if n in MA_PERIODS else c - ema(c, n),
                             rolling_std(c, n, 1))
    for n in RSI_PERIODS:
        f[f"rsi{n}"] = momentum.rsi(c, n)
    f["srsi_k"] = momentum.stochrsi(c)["k"]
    f["wr14"] = momentum.wr(h, lo, c, 14)
    f["cci14"] = momentum.cci(h, lo, c, 14)
    f["vwap_s"] = anchored.session_vwap(h, lo, c, v, ss)
    f["dist_vwap_atr"] = div(c - f["vwap_s"], f["atr14"])

    # --- momento ---------------------------------------------------------------------------
    f["macd_hist"] = momentum.macd(c)["hist"]
    m = momentum.mtm(c, 12, 6)
    f["mtm"], f["mamtm"] = m["mtm"], m["mamtm"]
    tx = momentum.trix(c, 12, 9)
    f["trix"], f["matrix"] = tx["trix"], tx["matrix"]
    for n in ROC_PERIODS:
        f[f"roc{n}"] = div(c - shift(c, n), shift(c, n))
    f["streak"] = _streak(c)
    k9 = momentum.kdj(h, lo, c)
    f["kdj_k"], f["kdj_d"] = k9["k"], k9["d"]

    # --- volumen y flujo de agresores ------------------------------------------------------
    for n in VOL_PERIODS:
        f[f"vol_rel{n}"] = div(v, sma(v, n))
    f["mfi14"] = volume.mfi(h, lo, c, v, 14)
    ob = volume.obv(c, v, 30)
    f["obv_slope"] = ob["obv"] - shift(ob["obv"], 6)
    f["delta1"] = div(s.taker_buy_v, v)
    f["delta6"] = div(sma(s.taker_buy_v, 6), sma(v, 6))
    cvd = anchored.session_cvd(v, s.taker_buy_v, ss)
    f["cvd_slope"] = cvd - shift(cvd, 6)
    size = div(v, s.trades)
    f["tsize_rel"] = div(size, sma(size, 20))
    em = volume.emv(h, lo, v, 14, 9)
    f["emv"], f["maemv"] = em["emv"], em["maemv"]

    # --- contexto de marco mayor y hora de la sesión ---------------------------------------
    f["h1_side"] = anchored.hourly_trend(s.t, c, 50)
    f["bars_in"] = anchored.bars_in_session(ss).astype(float)
    return f
