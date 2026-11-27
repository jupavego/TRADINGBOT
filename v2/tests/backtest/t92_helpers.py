"""Instrumentos, velas y estrategias de prueba de T92 (sin red; fixtures sintéticas de T90)."""
from __future__ import annotations

import json
from pathlib import Path

from eim.backtest.strategy import Signal
from eim.core import Candle, MarketSnapshot
from eim.data.adjust import PriceEvent
from eim.instruments.models import (
    AssetClass,
    DataCapability,
    Instrument,
    MarketStructure,
    SessionKind,
    TradableLevel,
)

FIX = Path(__file__).parents[1] / "fixtures" / "t90"
DAY = 86_400_000
H = 3_600_000
VOL = frozenset({DataCapability.CANDLES, DataCapability.REAL_VOLUME})


def equity(symbol: str = "ACME", lot: float = 1.0) -> Instrument:
    return Instrument(
        id=f"equity.nyse.{symbol}", symbol=symbol, label=symbol, asset_class=AssetClass.EQUITY,
        market_structure=MarketStructure.CONTINUOUS_BOOK, venue="nyse", currency="USD",
        quote_currency="USD", calendar_id="XNYS", session=SessionKind.EXCHANGE_HOURS, lot=lot,
        tick=0.01, data_capabilities=VOL, source="prueba T92")


def fx(symbol: str = "EURUSD") -> Instrument:
    quote = symbol[3:]
    return Instrument(
        id=f"fx.ecb.{symbol}", symbol=symbol, label=symbol, asset_class=AssetClass.FX,
        market_structure=MarketStructure.QUOTE_DRIVEN, venue="ecb", currency=quote,
        quote_currency=quote, calendar_id="24/5", session=SessionKind.WEEKDAYS,
        tradable_level=TradableLevel.OPERATIONAL,
        data_capabilities=frozenset({DataCapability.CANDLES}), source="prueba T92")


def future(symbol: str = "CLX", multiplier: float = 1000.0, expiry: int | None = None
           ) -> Instrument:
    return Instrument(
        id=f"future.cme.{symbol}", symbol=symbol, label=symbol, asset_class=AssetClass.FUTURE,
        market_structure=MarketStructure.CONTINUOUS_BOOK, venue="cme", currency="USD",
        quote_currency="USD", calendar_id="CMES", session=SessionKind.EXCHANGE_HOURS,
        tick=0.01, multiplier=multiplier, expiry=expiry, data_capabilities=VOL,
        source="prueba T92")


def load(name: str) -> tuple[dict, list[Candle], list[PriceEvent]]:
    d = json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))
    cs = [Candle(t=c[0], o=c[1], h=c[2], l=c[3], c=c[4], v=c[5]) for c in d["candles"]]
    return d, cs, [PriceEvent(**e) for e in d.get("events", [])]


def line(n: int, p0: float = 100.0, slope: float = 0.0, t0: int = 0, step: int = DAY,
         wick: float = 0.002, v: float = 1e6) -> list[Candle]:
    """Velas deterministas en línea recta, con mecha relativa `wick`."""
    out = []
    for i in range(n):
        o = p0 + slope * i
        c = o + slope
        out.append(Candle(t=t0 + i * step, o=o, h=max(o, c) * (1 + wick),
                          l=min(o, c) * (1 - wick), c=c, v=v))
    return out


class At:
    """Estrategia guionizada: en la vela de índice `i` (contando el snapshot completo) emite
    lado y SL/TP como fracción del cierre. Guarda lo que vio para la prueba de anticipación."""

    def __init__(self, plan: dict[int, tuple[int, float, float]]) -> None:
        self.plan = plan
        self.seen: list[MarketSnapshot] = []

    def on_bar(self, snap: MarketSnapshot) -> Signal | None:
        self.seen.append(snap)
        i = len(snap.candles) - 1
        if i not in self.plan:
            return None
        side, sl_f, tp_f = self.plan[i]
        c = snap.candles[-1].c
        return Signal(side, c * (1 - side * sl_f), c * (1 + side * tp_f), tag=str(i))
