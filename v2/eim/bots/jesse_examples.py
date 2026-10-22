"""Adaptador modo A de `jesse-example-strategies` (MIT, aprobado 2026-10-20): reglas portadas.

Se porta la **regla** de cada estrategia (`should_long/should_short/update_position`), no el
framework de Jesse. Indicadores de `eim.indicators` (idénticos a TA-Lib en RSI/SMA/EMA). Estados
como en Jesse: sin posición se evalúa la entrada (largo antes que corto); con posición, la salida
(`update_position`); una vela de salida no vuelve a entrar en esa misma vela. La postura es la
posición tras cada vela cerrada: +1 / 0 / −1. Stop-loss, take-profit, tamaño y pirámide son de
ejecución y NO se simulan (T59 pone su propia geometría); queda dicho en la evidencia.

Portadas (6 de 11): Donchian, RSI2, SMACrossover, MACD_EMA, TradingView_RSI, TurtleRules.
No portadas: IFR2 y SimpleBollinger (nube Ichimoku con parámetros propios), KDJstrategy (usa
`J > (K and D)`, que en Python es `J > D` por cortocircuito: una regla accidental que no se copia),
MAGen (tipo de media 11 elegido por índice de un catálogo de Jesse), DUAL_THRUST (vela ancla de un
marco superior aún abierta: anticipación). Origen y licencia: `THIRD_PARTY.md`.
Cada estrategia ve solo las últimas `WINDOW` velas, como el servicio y el relleno: así el estado
no depende de dónde empiece la historia disponible.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from eim.bots.adapter import empty_signal, quality_of, version_of
from eim.bots.card import BotCard, card_of
from eim.core import BotSignal, Candle, MarketSnapshot
from eim.indicators._core import ema, rolling_max, rolling_min, shift, sma
from eim.indicators.momentum import rsi

BOT_ID = "jesse-example-strategies"
WINDOW = 1000
WARMUP = 210   # velas de arranque de la ventana: antes no se evalúa nada (SMA 200 + holgura)
NOTE_EXITS = ("salida solo por regla: stop-loss, take-profit, tamaño y pirámide del bot son de "
              "ejecución y no se simulan")

# (entrada larga, entrada corta, salida de largo, salida de corto) por vela
Flags = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
Arrays = dict[str, np.ndarray]

PARAMS: dict[str, dict] = {
    "Donchian": {"period": 20, "sma": 200},
    "RSI2": {"sma_slow": 200, "sma_fast": 5, "rsi": 2, "ob": 90, "os": 10},
    "SMACrossover": {"fast": 50, "slow": 200},
    "MACD_EMA": {"ema": 100, "fast": 12, "slow": 26, "signal": 9},
    "TradingView_RSI": {"rsi": 5, "entry": 35, "exit": 75, "emergency": 10},
    "TurtleRules": {"entry": 20, "exit": 10},
}


def _no(n: int) -> np.ndarray:
    return np.zeros(n, dtype=bool)


def crossed(s: np.ndarray, level: float, above: bool) -> np.ndarray:
    """`jesse.utils.crossed`: arriba = s[t] > nivel y s[t−1] ≤ nivel (abajo, al revés)."""
    p = shift(s, 1)
    with np.errstate(invalid="ignore"):
        return (s > level) & (p <= level) if above else (s < level) & (p >= level)


def _macd(close: np.ndarray, fast: int, slow: int, signal: int) -> tuple[np.ndarray, np.ndarray]:
    dif = ema(close, fast, "sma") - ema(close, slow, "sma")
    return dif, ema(dif, signal, "sma")


def _donchian(a: Arrays, p: dict) -> Flags:
    # Jesse: canal del período anterior (`candles[:-1]`) y filtro de tendencia SMA
    up, lo = shift(rolling_max(a["h"], p["period"]), 1), shift(rolling_min(a["l"], p["period"]), 1)
    c = a["c"]
    return (c > up) & (c > sma(c, p["sma"])), _no(len(c)), c < lo, _no(len(c))


def _rsi2(a: Arrays, p: dict) -> Flags:
    c = a["c"]
    slow, fast, r = sma(c, p["sma_slow"]), sma(c, p["sma_fast"]), rsi(c, p["rsi"])
    return (c > slow) & (r <= p["os"]), (c < slow) & (r >= p["ob"]), c > fast, c < fast


def _sma_cross(a: Arrays, p: dict) -> Flags:
    f, s = sma(a["c"], p["fast"]), sma(a["c"], p["slow"])
    return f > s, f < s, f < s, f > s


def _macd_ema(a: Arrays, p: dict) -> Flags:
    c = a["c"]
    line, sig = _macd(c, p["fast"], p["slow"], p["signal"])
    e = ema(c, p["ema"], "sma")
    return (c > e) & (line > sig), _no(len(c)), (line < sig) & (c < e), _no(len(c))


def _tv_rsi(a: Arrays, p: dict) -> Flags:
    r = rsi(a["c"], p["rsi"])
    out = crossed(r, p["exit"], False) | crossed(r, p["emergency"], False)
    return crossed(r, p["entry"], True), _no(len(r)), out, _no(len(r))


def _turtle(a: Arrays, p: dict) -> Flags:
    """Sistema 1: canal Donchian que INCLUYE la vela actual (como `jesse.indicators.donchian`)."""
    h, lo = a["h"], a["l"]
    up_e, lo_e = rolling_max(h, p["entry"]), rolling_min(lo, p["entry"])
    up_x, lo_x = rolling_max(h, p["exit"]), rolling_min(lo, p["exit"])
    with np.errstate(invalid="ignore"):
        long_e = h >= up_e
        short_e = ~long_e & (lo <= lo_e)               # entry_signal: largo antes que corto
        exit_short_sig = h >= up_x
        exit_long_sig = ~exit_short_sig & (lo <= lo_x)  # exit_signal: igual precedencia
    return long_e, short_e, short_e | exit_long_sig, long_e | exit_short_sig


STRATEGIES: dict[str, Callable[[Arrays, dict], Flags]] = {
    "Donchian": _donchian, "RSI2": _rsi2, "SMACrossover": _sma_cross, "MACD_EMA": _macd_ema,
    "TradingView_RSI": _tv_rsi, "TurtleRules": _turtle}


def jesse_positions(flags: Flags) -> np.ndarray:
    """Posición tras cada vela con la mecánica de Jesse (entrada solo plano; salida solo dentro)."""
    el, es, xl, xs = flags
    out, state = np.zeros(len(el), dtype=int), 0
    for i in range(WARMUP - 1, len(el)):
        if state == 0:
            state = 1 if el[i] else (-1 if es[i] else 0)
        elif (state > 0 and xl[i]) or (state < 0 and xs[i]):
            state = 0
        out[i] = state
    return out


def arrays_of(candles: list[Candle]) -> Arrays:
    return {k: np.array([getattr(c, k) for c in candles], dtype=float) for k in "ohlcv"}


def stance_series(candles: list[Candle], strategy: str, params: dict | None = None) -> np.ndarray:
    """Postura en cada vela con solo las últimas `WINDOW` velas hasta ella (NaN sin ventana)."""
    out = np.full(len(candles), np.nan)
    p = params or PARAMS[strategy]
    for i in range(WINDOW - 1, len(candles)):
        out[i] = jesse_positions(STRATEGIES[strategy](
            arrays_of(candles[i + 1 - WINDOW:i + 1]), p))[-1]
    return out


class JesseExamplesAdapter:
    """Modo A: función pura sobre el snapshot. Una señal por estrategia portada."""

    bot_id = BOT_ID
    timeframes = ("1h",)
    history_bars = WINDOW

    def __init__(self, card: BotCard | None = None, strategies: tuple[str, ...] | None = None
                 ) -> None:
        self.card = card or card_of(BOT_ID)
        self.strategies = strategies or tuple(STRATEGIES)

    def version(self, strategy: str) -> str:
        return version_of(self.card.commit_sha, {"strategy": strategy, **PARAMS[strategy]})

    def signals(self, snapshot: MarketSnapshot) -> list[BotSignal]:
        return [self._one(snapshot, s) for s in self.strategies]

    def _one(self, snap: MarketSnapshot, name: str) -> BotSignal:
        ver = self.version(name)
        if len(snap.candles) < WINDOW:
            return empty_signal(self.card, name, ver, snap, "no_data",
                                f"velas insuficientes: {len(snap.candles)} < {WINDOW}", WINDOW)
        pos = jesse_positions(STRATEGIES[name](arrays_of(snap.candles[-WINDOW:]), PARAMS[name]))
        stance = float(pos[-1])
        held = next((k for k in range(len(pos)) if pos[len(pos) - 1 - k] != pos[-1]), len(pos))
        return BotSignal(
            bot_id=self.card.id, strategy=name, version=ver, asof=snap.asof,
            timeframe=snap.timeframe, symbol=snap.symbol, stance=stance, confidence=None,
            evidence=[f"{name}: postura {stance:g} (mantenida {held} velas); regla portada de "
                      f"{BOT_ID}; {NOTE_EXITS}"],
            raw={"signal": int(stance), "held_bars": held},
            data_quality=quality_of(snap, WINDOW, NOTE_EXITS), status="ok")
