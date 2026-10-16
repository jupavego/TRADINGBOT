"""Constructores sintéticos para los tests del bróker simulado (sin red)."""

from __future__ import annotations

from eim.core import Candle
from eim.paper.ideas import Idea

M15 = 15 * 60_000
H1 = 3_600_000
T0 = 1_760_000_000_000 // H1 * H1          # múltiplo de 1 h y de 8 h no garantizado


def bar(t: int, o: float, h: float, lo: float, c: float) -> Candle:
    return Candle(t=t, o=o, h=h, l=lo, c=c, v=1000.0)


def flat(n: int, price: float = 100.0, t0: int = T0, step: int = M15,
         spread: float = 0.2) -> list[Candle]:
    """`n` velas planas alrededor de `price` (no tocan niveles lejanos)."""
    return [bar(t0 + i * step, price, price + spread, price - spread, price) for i in range(n)]


def with_bar(cs: list[Candle], i: int, o: float, h: float, lo: float, c: float) -> list[Candle]:
    out = list(cs)
    out[i] = bar(cs[i].t, o, h, lo, c)
    return out


def idea(side: int = 1, kind: str = "market", entry: float = 100.0, sl: float = 98.0,
         tp: float = 104.0, t: int = T0, strategy: str = "s", family: str = "consenso",
         fill_h: float = 0.0, hold_h: float = 24.0, conf: float = 0.5, key: str = "",
         syn_bias: float = 0.5, iid: str | None = None) -> Idea:
    return Idea(id=iid or f"X:{t}:{strategy}", strategy=strategy, family=family, symbol="X", t=t,
                side=side, kind=kind, entry=entry, sl=sl, tp=tp,
                fill_ms=int(fill_h * H1) if kind == "limit" else 0, hold_ms=int(hold_h * H1),
                conf=conf, why=("test",), key=key, syn_bias=syn_bias)
