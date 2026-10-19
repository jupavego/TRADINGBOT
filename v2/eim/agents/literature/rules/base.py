"""Contexto numérico y tipos comunes de las reglas de la literatura (puro)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from eim.agents.literature.params import LiteratureParams
from eim.core import MarketSnapshot
from eim.indicators.momentum import rsi
from eim.indicators.volatility import atr


@dataclass(frozen=True)
class Condition:
    """Condición evaluada con el valor medido (nunca se afirma sin su cifra)."""

    name: str
    value: float | str
    ok: bool = True


@dataclass(frozen=True)
class RuleHit:
    card_id: str
    direction: int          # +1 alcista, −1 bajista
    strength: float         # 0..1
    horizon_bars: int
    t: int                  # vela (cierre) donde se cumple
    price: float
    timeframe: str
    conditions: tuple[Condition, ...] = field(default_factory=tuple)
    label: str = ""


@dataclass(frozen=True)
class Ctx:
    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    lo: np.ndarray
    c: np.ndarray
    v: np.ndarray
    atr: np.ndarray
    rsi: np.ndarray
    timeframe: str

    @classmethod
    def of(cls, snap: MarketSnapshot, p: LiteratureParams) -> Ctx:
        cs = snap.candles
        a = lambda k: np.array([getattr(x, k) for x in cs], dtype=float)  # noqa: E731
        h, lo, c = a("h"), a("l"), a("c")
        return cls(t=np.array([x.t for x in cs]), o=a("o"), h=h, lo=lo, c=c, v=a("v"),
                   atr=atr(h, lo, c, p.atr_period), rsi=rsi(c, p.rsi_period),
                   timeframe=snap.timeframe)

    # --- medidas de una vela ------------------------------------------------------------------
    def body(self, i: int) -> float:
        return abs(self.c[i] - self.o[i])

    def rng(self, i: int) -> float:
        return self.h[i] - self.lo[i]

    def top(self, i: int) -> float:
        return max(self.o[i], self.c[i])

    def bot(self, i: int) -> float:
        return min(self.o[i], self.c[i])

    def white(self, i: int) -> bool:
        return self.c[i] > self.o[i]

    def black(self, i: int) -> bool:
        return self.c[i] < self.o[i]

    def trend(self, i: int, p: LiteratureParams) -> float:
        """Cambio del cierre en `trend_bars` velas que terminan en `i`, en ATR (+ = alza)."""
        j = i - p.trend_bars
        if j < 0 or not self.atr[i] > 0:
            return float("nan")
        return float((self.c[i] - self.c[j]) / self.atr[i])

    def vol_high(self, i: int, p: LiteratureParams) -> bool:
        w = self.v[max(0, i - p.vol_window):i]
        return len(w) > 0 and w.mean() > 0 and self.v[i] > p.vol_ratio * w.mean()


Rule = Callable[[Ctx, LiteratureParams, int], RuleHit | None]


@dataclass(frozen=True)
class RuleSpec:
    card_id: str
    fn: Rule
    min_bars: Callable[[LiteratureParams, str], int]  # velas necesarias (params, marco)


def clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))
