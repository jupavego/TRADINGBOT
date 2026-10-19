"""Adaptador modo A de `hummingbot-directional` (Apache-2.0, T56 aprobado): reglas portadas.

Se porta la **regla** (≈10 líneas por controlador de `controllers/directional_trading/`), no el
framework: sin Hummingbot, sin `pandas-ta` (sin licencia) y sin I/O. Los indicadores salen de
`eim.indicators` (T34). Como el bot nativo, cada controlador ve solo sus últimas `max_records`
velas. Origen y licencia: `THIRD_PARTY.md`. `signal` ∈ {+1, 0, −1}; el bot no da confianza.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict

from eim.bots.adapter import empty_signal, quality_of, version_of
from eim.bots.card import BotCard, card_of
from eim.core import BotSignal, Candle, MarketSnapshot
from eim.indicators._core import ema, rolling_std, sma

BOT_ID = "hummingbot-directional"


class BollingerV1(BaseModel):
    """`bollinger_v1`: largo si %B < umbral inferior, corto si > superior."""

    model_config = ConfigDict(frozen=True)
    bb_length: int = 100
    bb_std: float = 2.0
    bb_long_threshold: float = 0.0
    bb_short_threshold: float = 1.0

    @property
    def max_records(self) -> int:
        return self.bb_length


class MacdBbV1(BaseModel):
    """`macd_bb_v1`: %B fuera de banda y MACD que ya gira (histograma) contra su signo."""

    model_config = ConfigDict(frozen=True)
    bb_length: int = 100
    bb_std: float = 2.0
    bb_long_threshold: float = 0.0
    bb_short_threshold: float = 1.0
    macd_fast: int = 21
    macd_slow: int = 42
    macd_signal: int = 9

    @property
    def max_records(self) -> int:
        return max(self.macd_slow, self.macd_fast, self.macd_signal, self.bb_length) + 20


def _bbp(close: np.ndarray, length: int, std: float) -> np.ndarray:
    """%B como lo calcula el bot nativo: SMA ± k·σ muestral (`pandas-ta` usa ddof=1; la parity
    contra el bot real lo detectó: con ddof=0 el %B difería hasta 0,005)."""
    mid, sd = sma(close, length), rolling_std(close, length, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (close - (mid - std * sd)) / (2 * std * sd)


def _macd(close: np.ndarray, fast: int, slow: int, signal: int) -> tuple[np.ndarray, np.ndarray]:
    """MACD de `pandas-ta`: EMAs sembradas con la SMA de sus primeros datos; (línea, histograma)."""
    dif = ema(close, fast, "sma") - ema(close, slow, "sma")
    return dif, dif - ema(dif, signal, "sma")


def _bollinger(close: np.ndarray, p: BollingerV1) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    bbp = _bbp(close, p.bb_length, p.bb_std)
    sig = np.where(bbp < p.bb_long_threshold, 1, np.where(bbp > p.bb_short_threshold, -1, 0))
    return sig, {"bbp": bbp}


def _macd_bb(close: np.ndarray, p: MacdBbV1) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    bbp = _bbp(close, p.bb_length, p.bb_std)
    dif, hist = _macd(close, p.macd_fast, p.macd_slow, p.macd_signal)
    long_ = (bbp < p.bb_long_threshold) & (hist > 0) & (dif < 0)
    short = (bbp > p.bb_short_threshold) & (hist < 0) & (dif > 0)
    sig = np.where(long_, 1, np.where(short, -1, 0))
    return sig, {"bbp": bbp, "macd": dif, "macdh": hist}


STRATEGIES = {"bollinger_v1": (BollingerV1(), _bollinger),
              "macd_bb_v1": (MacdBbV1(), _macd_bb)}


def stance_series(candles: list[Candle], strategy: str, params=None) -> np.ndarray:
    """Postura en cada vela como la daría el bot con solo las velas hasta ella (vectorizado).

    NaN donde el bot aún no tiene datos. Existe para probar la no anticipación: calcular sobre
    un prefijo de las velas da lo mismo que esta serie en esa posición.
    """
    default, fn = STRATEGIES[strategy]
    p = params or default
    close = np.array([c.c for c in candles], dtype=float)
    out = np.full(len(close), np.nan)
    for i in range(p.max_records - 1, len(close)):
        sig, feats = fn(close[i + 1 - p.max_records:i + 1], p)
        if not any(np.isnan(v[-1]) for v in feats.values()):
            out[i] = sig[-1]
    return out


class HummingbotDirectionalAdapter:
    """Modo A: función pura sobre el snapshot. Una señal por estrategia portada."""

    bot_id = BOT_ID

    def __init__(self, card: BotCard | None = None,
                 strategies: dict[str, BollingerV1 | MacdBbV1] | None = None) -> None:
        self.card = card or card_of(BOT_ID)
        self.params = strategies or {k: v[0] for k, v in STRATEGIES.items()}

    def version(self, strategy: str) -> str:
        return version_of(self.card.commit_sha, {"strategy": strategy,
                                                 **self.params[strategy].model_dump()})

    def signals(self, snapshot: MarketSnapshot) -> list[BotSignal]:
        return [self._one(snapshot, name) for name in self.params]

    def _one(self, snap: MarketSnapshot, name: str) -> BotSignal:
        p = self.params[name]
        ver = self.version(name)
        n = p.max_records
        if len(snap.candles) < n:
            return empty_signal(self.card, name, ver, snap, "no_data",
                                f"velas insuficientes: {len(snap.candles)} < {n}", n)
        window = snap.candles[-n:]
        _, fn = STRATEGIES[name]
        close = np.array([c.c for c in window], dtype=float)
        sig, feats = fn(close, p)
        last = {k: float(v[-1]) for k, v in feats.items()}
        if any(np.isnan(v) for v in last.values()):
            return empty_signal(self.card, name, ver, snap, "no_data",
                                "indicadores sin valor en la última vela", n)
        stance = float(sig[-1])
        return BotSignal(
            bot_id=self.card.id, strategy=name, version=ver, asof=snap.asof,
            timeframe=snap.timeframe, symbol=snap.symbol, stance=stance, confidence=None,
            evidence=[_why(name, stance, last, p)],
            raw={"signal": int(stance), **{k: round(v, 6) for k, v in last.items()}},
            data_quality=quality_of(snap, n), status="ok")


def _why(name: str, stance: float, f: dict[str, float], p) -> str:
    side = {1.0: "largo", -1.0: "corto", 0.0: "plano"}[stance]
    return (f"{name}: %B={f['bbp']:.3f} (umbrales {p.bb_long_threshold}/{p.bb_short_threshold}) "
            f"→ {side}; regla portada de {BOT_ID}")
