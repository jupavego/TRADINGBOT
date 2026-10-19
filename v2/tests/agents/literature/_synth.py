"""Velas sintéticas deterministas para las reglas del agente `literature` (sin red)."""
from __future__ import annotations

from eim.core import Candle, MarketSnapshot

HOUR = 3_600_000
T0 = 1_700_000_000_000 // HOUR * HOUR


def trend(direction: int, n: int = 90, start: float = 1000.0, step: float = 0.5,
          vol: float = 1000.0) -> list[tuple]:
    """Tendencia lineal limpia (cuerpos de 0,5; ATR ≈ 1,4): `direction` ±1."""
    out, price = [], start
    for _ in range(n):
        o, c = price, price + direction * step
        out.append((o, max(o, c) + 0.2, min(o, c) - 0.2, c, vol))
        price = c
    return out


def flat(n: int = 90, level: float = 1000.0) -> list[tuple]:
    return [(level, level + 0.7, level - 0.7, level, 1000.0)] * n


def snap(bars: list[tuple], tf: str = "1h") -> MarketSnapshot:
    cs = [Candle(t=T0 + k * HOUR, o=o, h=h, l=lo, c=c, v=v) for k, (o, h, lo, c, v)
          in enumerate(bars)]
    return MarketSnapshot(symbol="BTCUSDT", timeframe=tf, candles=cs, asof=cs[-1].t + HOUR,
                          sources={"candles": "sintético"},
                          coverage={"candles": (cs[0].t, cs[-1].t)})


def ohlc(o: float, c: float, up: float = 0.1, dn: float = 0.1, v: float = 1000.0) -> tuple:
    return (o, max(o, c) + up, min(o, c) - dn, c, v)
