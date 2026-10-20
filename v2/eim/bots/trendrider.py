"""Adaptador modo A de `trendrider-strategy` (MIT, aprobado 2026-10-20): regla portada.

`TrendRiderStrategy` (Freqtrade, 1 h, solo largos) reescrita con numpy: seis entradas
(pullback a EMA, rebote en EMA50, rebote de RSI, cruce de EMAs, rebote en Bollinger, giro del
histograma MACD), cuatro salidas por señal, y el filtro de confianza de `confirm_trade_entry`
(≥ 5/10, ≥ 6 en régimen bajista). Parámetros = `buy_params`/`sell_params` de la estrategia
(resultado de su hyperopt; EIM no los ajusta). Indicadores como TA-Lib (EMA/RSI/ADX/DI/MACD/BBANDS/
OBV; ver `trendrider_ind.py`) y marcos 4 h y 1 d agregados desde las velas de 1 h, visibles solo
tras cerrarse (`merge_informative_pair`). Solo BTCUSDT: «BTC como sentimiento» es su propio RSI.
Sin FNG ni funding (la versión pública los fija en neutro: 50 y 0) ni red.
Fuera de la postura (ejecución, no se simulan): ROI, stoploss −6 %, trailing, `custom_exit`
(cortes por tiempo/pérdida), protecciones. Hace falta historia larga: la EMA200 diaria pide ≥ 200
velas de 1 d; la ventana es de `WINDOW` velas de 1 h (225 días) y sin ella el bot no opina
(`no_data`), igual que el bot nativo con NaN. Origen y licencia: `THIRD_PARTY.md`.
"""

from __future__ import annotations

import numpy as np

from eim.bots.adapter import empty_signal, quality_of, version_of
from eim.bots.card import BotCard, card_of
from eim.bots.ft_adapter import positions
from eim.bots.trendrider_ind import adx_di, bbands, informative, macd, obv
from eim.core import BotSignal, MarketSnapshot
from eim.indicators._core import ema, shift
from eim.indicators.momentum import rsi

BOT_ID = "trendrider-strategy"
STRATEGY = "TrendRiderStrategy"
WINDOW = 5400            # velas de 1 h (225 días): EMA200 diaria con su arranque
STARTUP = 210            # startup_candle_count de la estrategia
PARAMS = {"ema_fast": 9, "ema_slow": 16, "rsi_period": 16, "rsi_pullback_low": 30,
          "rsi_pullback_high": 65, "rsi_bounce": 35, "adx_threshold": 18, "volume_factor": 0.7,
          "rsi_exit": 78, "min_confidence": 5, "min_confidence_bear": 6}
NOTE_EXITS = ("salida solo por señal: ROI, stoploss, trailing y cortes por tiempo del bot son de "
              "ejecución y no se simulan")


def _lt(a, b):   # comparaciones con NaN = False, como pandas
    with np.errstate(invalid="ignore"):
        return a < b


def _gt(a, b):
    with np.errstate(invalid="ignore"):
        return a > b


def indicators(o, h, lo, c, v, t) -> dict[str, np.ndarray]:
    """Columnas de `populate_indicators` que usan las reglas (más las informativas alineadas)."""
    p = PARAMS
    d: dict[str, np.ndarray] = {"open": o, "high": h, "low": lo, "close": c, "volume": v}
    d["ema_fast"], d["ema_slow"] = ema(c, p["ema_fast"], "sma"), ema(c, p["ema_slow"], "sma")
    d["ema_50"], d["ema_200"] = ema(c, 50, "sma"), ema(c, 200, "sma")
    d["rsi"], d["rsi_14"] = rsi(c, p["rsi_period"]), rsi(c, 14)
    d["adx"], d["plus_di"], d["minus_di"] = adx_di(h, lo, c, 14)
    _, _, hist = macd(c)
    d["macdhist"], d["macdhist_prev"] = hist, shift(hist, 1)
    d["bb_upper"], d["bb_middle"], d["bb_lower"] = bbands(c, 20, 2.0)
    d["volume_ratio"] = v / (ema(v, 20, "sma") + 1e-10)
    ob = obv(c, v)
    d["obv"], d["obv_ema"] = ob, ema(ob, 20, "sma")
    d["is_bull"] = (_gt(c, d["ema_200"]) & _gt(d["ema_50"], d["ema_200"])).astype(int)
    # informativos (cada uno se ve cuando su vela de 4 h / 1 d ya cerró)
    i4 = informative(t, o, h, lo, c, 4 * 3_600_000)
    e50, e200 = ema(i4.c, 50, "sma"), ema(i4.c, 200, "sma")
    bull4 = (_gt(i4.c, e200) & _gt(e50, e200)).astype(float)
    d["is_bull_4h"], d["adx_4h"] = i4.align(bull4, t), i4.align(adx_di(i4.h, i4.l, i4.c,
                                                                        14)[0], t)
    i1 = informative(t, o, h, lo, c, 24 * 3_600_000)
    d["ema_200_1d"] = i1.align(ema(i1.c, 200, "sma"), t)
    return d


def entries(d: dict[str, np.ndarray]) -> np.ndarray:
    """`enter_long`: alguna de las seis condiciones (FNG neutro, BTC = RSI 14 propio)."""
    p, c, rsi_, ok = PARAMS, d["close"], d["rsi"], d["volume"] > 0
    btc = _gt(d["rsi_14"], 35)
    bull = d["is_bull"] == 1
    bounce_up = c > d["open"]
    pull = (_lt(d["low"], d["ema_slow"] * 1.02) & _gt(c, d["ema_slow"]) & bounce_up)
    e50 = (_lt(d["low"], d["ema_50"] * 1.01) & _gt(c, d["ema_50"]) & bounce_up)
    long1 = (bull & pull & _gt(rsi_, p["rsi_pullback_low"]) & _lt(rsi_, p["rsi_pullback_high"])
             & _gt(d["adx"], p["adx_threshold"]) & _gt(d["volume_ratio"], p["volume_factor"])
             & _gt(d["plus_di"], d["minus_di"]) & _gt(d["obv"], d["obv_ema"]) & ok & btc
             & _lt(rsi_, 70) & _gt(c, d["ema_200_1d"]))
    long2 = (bull & e50 & _gt(rsi_, 30) & _lt(rsi_, 50) & _gt(d["adx"], 20)
             & _gt(d["volume_ratio"], 1.0) & _gt(d["macdhist"], d["macdhist_prev"]) & ok & btc
             & _lt(rsi_, 70))
    long3 = (_gt(c, d["ema_200"]) & _lt(shift(rsi_, 1), p["rsi_bounce"])
             & _gt(rsi_, p["rsi_bounce"]) & _gt(c, d["bb_lower"]) & bounce_up
             & _gt(d["volume_ratio"], 0.8)
             & _gt(d["obv"], d["obv_ema"]) & ok & btc)
    cross = _gt(d["ema_fast"], d["ema_slow"]) & (shift(d["ema_fast"], 1) <= shift(d["ema_slow"], 1))
    long4 = (cross & _gt(rsi_, 40) & _lt(rsi_, 75) & _gt(c, d["ema_200"])
             & _gt(d["volume_ratio"], 0.5) & ok & btc)
    long5 = (_lt(c, d["bb_lower"] * 1.005) | (c == d["bb_lower"] * 1.005)) & bounce_up \
        & _lt(rsi_, 45) & _gt(d["volume_ratio"], 0.7) & _gt(d["adx"], 18) & ok & btc
    long6 = (_gt(d["macdhist"], 0) & (d["macdhist_prev"] <= 0) & _gt(c, d["ema_50"])
             & _gt(c, d["ema_200"]) & _gt(rsi_, 40) & _lt(rsi_, 60) & _gt(d["adx"], 15)
             & _gt(d["volume_ratio"], 0.8) & ok & btc)
    return long1 | long2 | long3 | long4 | long5 | long6


def exits(d: dict[str, np.ndarray]) -> np.ndarray:
    """`exit_long`: RSI sobrecomprado, cruce bajista, tendencia rota, aviso temprano."""
    c, rsi_, ok = d["close"], d["rsi"], d["volume"] > 0
    e200 = d["ema_200"]
    x1 = _gt(rsi_, PARAMS["rsi_exit"]) & ok
    x2 = (_lt(d["ema_fast"], d["ema_slow"]) & (shift(d["ema_fast"], 1) >= shift(d["ema_slow"], 1))
          & _lt(d["macdhist"], 0) & _gt(rsi_, 50) & ok)
    x3 = _lt(c, e200 * 0.99) & (shift(c, 1) >= shift(e200, 1)) & ok
    x4 = (_lt(c, e200 * 0.995) & _gt(rsi_, 72) & _lt(d["macdhist"], d["macdhist_prev"]) & ok)
    return x1 | x2 | x3 | x4


def confidence(d: dict[str, np.ndarray]) -> np.ndarray:
    """`_calc_confidence` (1..10) en cada vela; FNG 50 y funding 0 como la versión pública."""
    p, s = PARAMS, np.zeros(len(d["close"]))
    r, adx, vr, mh = d["rsi"], d["adx"], d["volume_ratio"], d["macdhist"]
    s += 1.5 * (_gt(r, 35) & _lt(r, 60))
    s += np.where(_gt(adx, 30), 2.5, np.where(_gt(adx, p["adx_threshold"]), 1.5, 0.0))
    s += np.where(_gt(vr, 1.5), 2.5, np.where(_gt(vr, 1.0), 1.5, 0.0))
    s += np.where(_gt(mh, 0), 1.5 + 0.5 * _gt(mh, d["macdhist_prev"]), 0.0)
    s += 1.5 * _gt(d["obv"], d["obv_ema"])
    s += 1.5 * (_gt(d["rsi_14"], 40) & _lt(d["rsi_14"], 70))            # BTC saludable
    s += 1.5 * ((d["is_bull_4h"] == 1) & _gt(d["adx_4h"], 20))
    rng = np.where(d["bb_upper"] > d["bb_lower"], d["bb_upper"] - d["bb_lower"], 1.0)
    s += 1.0 * (_gt(d["bb_lower"], 0) & _lt((d["close"] - d["bb_lower"]) / rng, 0.35))
    s += 1.0 * _gt(d["plus_di"] - d["minus_di"], 10)
    s += 1.0 + 1.0                                                       # FNG neutro + funding sano
    return np.clip(np.round(s * 10 / 17.5), 1, 10)


def regime_bear(d: dict[str, np.ndarray]) -> np.ndarray:
    """`_get_market_regime` contiene «Bear»: ADX ≥ 20 y no (alcista con cierre > EMA200)."""
    bull = (d["is_bull"] == 1) & _gt(d["close"], d["ema_200"])
    return ~_lt(d["adx"], 20) & ~bull


def flags(d: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    conf = confidence(d)
    need = np.where(regime_bear(d), PARAMS["min_confidence_bear"], PARAMS["min_confidence"])
    enter = entries(d) & (conf >= need)
    n = len(enter)
    return {"enter_long": enter.astype(int), "exit_long": exits(d).astype(int),
            "enter_short": np.zeros(n, int), "exit_short": np.zeros(n, int)}


def stance_of(window: list) -> tuple[float, dict, int]:
    """(postura, banderas de la última vela, velas mantenida) de una ventana de `WINDOW` velas."""
    a = {k: np.array([getattr(x, k) for x in window], float) for k in "ohlcv"}
    t = np.array([x.t for x in window], dtype=np.int64)
    d = indicators(a["o"], a["h"], a["l"], a["c"], a["v"], t)
    fl = flags(d)
    pos = positions({k: v.tolist() for k, v in fl.items()}, False, STARTUP)
    held = next((k for k in range(len(pos)) if pos[len(pos) - 1 - k] != pos[-1]), len(pos))
    return float(pos[-1]), {k: int(v[-1]) for k, v in fl.items()}, held


class TrendRiderAdapter:
    """Modo A: función pura sobre el snapshot (solo 1 h, solo BTCUSDT)."""

    bot_id = BOT_ID
    timeframes = ("1h",)
    history_bars = WINDOW

    def __init__(self, card: BotCard | None = None) -> None:
        self.card = card or card_of(BOT_ID)

    def version(self, strategy: str = STRATEGY) -> str:
        return version_of(self.card.commit_sha, {"strategy": strategy, **PARAMS})

    def signals(self, snapshot: MarketSnapshot) -> list[BotSignal]:
        ver, snap = self.version(), snapshot
        if snap.symbol != "BTCUSDT":
            return [empty_signal(self.card, STRATEGY, ver, snap, "no_data",
                                 "usa el RSI de BTC como sentimiento: solo BTCUSDT")]
        if len(snap.candles) < WINDOW:
            return [empty_signal(self.card, STRATEGY, ver, snap, "no_data",
                                 f"velas insuficientes: {len(snap.candles)} < {WINDOW}", WINDOW)]
        stance, last, held = stance_of(snap.candles[-WINDOW:])
        return [BotSignal(
            bot_id=self.card.id, strategy=STRATEGY, version=ver, asof=snap.asof,
            timeframe=snap.timeframe, symbol=snap.symbol, stance=stance, confidence=None,
            evidence=[f"{STRATEGY}: postura {stance:g} (banderas de la última vela {last}; "
                      f"mantenida {held} velas); {NOTE_EXITS}"],
            raw={"flags_last": last, "held_bars": held},
            data_quality=quality_of(snap, WINDOW, NOTE_EXITS), status="ok")]
