"""Series e instrumentos sintéticos de T91: sesiones con huecos nocturnos y de fin de semana,
sin volumen o con volumen de ticks. Deterministas, sin red ni calendarios externos."""
from __future__ import annotations

import datetime as dt

import numpy as np

from eim.core import Candle, MarketSnapshot
from eim.instruments.models import (
    AssetClass,
    DataCapability,
    Instrument,
    MarketStructure,
    SessionKind,
    make_id,
)

HOUR = 3_600_000
DAY = 24 * HOUR
#: Lunes 2025-01-06 00:00 UTC.
MONDAY = int(dt.datetime(2025, 1, 6, tzinfo=dt.UTC).timestamp() * 1000)


def _walk(n: int, seed: int, gap_every: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(apertura, cierre): paseo aleatorio con salto de apertura cada `gap_every` velas."""
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    o = np.r_[c[0], c[:-1]].copy()
    if gap_every:
        jumps = rng.normal(0, 0.01, n)
        o[::gap_every] = o[::gap_every] * np.exp(jumps[::gap_every])  # hueco de apertura
    return o, c


def _bars(times: list[int], seed: int, volume: str, gap_every: int | None) -> list[Candle]:
    o, c = _walk(len(times), seed, gap_every)
    rng = np.random.default_rng(seed + 1)
    out = []
    for k, t in enumerate(times):
        h, lo = max(o[k], c[k]) * 1.002, min(o[k], c[k]) * 0.998
        v = {"real": 1000 + 100 * rng.random(), "tick": float(rng.integers(50, 500)),
             "none": 0.0}[volume]
        out.append(Candle(t=t, o=float(o[k]), h=float(h), l=float(lo), c=float(c[k]), v=v))
    return out


def session_hours(days: int, *, weekdays_only: bool = True, hours: range = range(15, 21)
                  ) -> list[int]:
    """Velas de 1 h de lunes a viernes (o todos los días) en las horas UTC dadas."""
    out = []
    for d in range(days):
        day = MONDAY + d * DAY
        if weekdays_only and dt.datetime.fromtimestamp(day / 1000, dt.UTC).weekday() >= 5:
            continue
        out += [day + h * HOUR for h in hours]
    return out


def equity_1h(days: int = 90, volume: str = "none", seed: int = 3) -> list[Candle]:
    """Sesión de Nueva York (15–20 h UTC), huecos nocturnos y de fin de semana."""
    return _bars(session_hours(days), seed, volume, gap_every=6)


def equity_1d(days: int = 420, volume: str = "none", seed: int = 5) -> list[Candle]:
    """Una vela por sesión (apertura 14:30 UTC), sin fines de semana."""
    times = [t + 14 * HOUR + 30 * 60_000 for t in session_hours(days, hours=range(0, 1))]
    return _bars(times, seed, volume, gap_every=1)


def fx_1h(days: int = 60, seed: int = 7) -> list[Candle]:
    """24/5 con volumen de ticks: todas las horas de lunes a viernes, hueco de fin de semana."""
    return _bars(session_hours(days, hours=range(24)), seed, "tick", gap_every=None)


def snapshot(symbol: str, timeframe: str, candles: list[Candle]) -> MarketSnapshot:
    step = HOUR if timeframe == "1h" else DAY
    return MarketSnapshot(symbol=symbol, timeframe=timeframe, candles=candles,
                          asof=candles[-1].t + step, sources={"candles": "sintética T91"},
                          coverage={"candles": (candles[0].t, candles[-1].t)})


def instrument(asset_class: AssetClass, symbol: str, calendar: str, session: SessionKind,
               caps: set[DataCapability], structure: MarketStructure) -> Instrument:
    return Instrument(
        id=make_id(asset_class, "synth", symbol), symbol=symbol, label=f"{symbol} sintético",
        asset_class=asset_class, market_structure=structure, venue="synth", currency="USD",
        quote_currency="USD", calendar_id=calendar, session=session,
        data_capabilities=frozenset(caps | {DataCapability.CANDLES}), source="test T91")


EQUITY = instrument(AssetClass.EQUITY, "ACME", "XNYS", SessionKind.EXCHANGE_HOURS,
                    {DataCapability.REAL_VOLUME}, MarketStructure.CONTINUOUS_BOOK)
FX = instrument(AssetClass.FX, "EURUSD", "24/5", SessionKind.WEEKDAYS,
                {DataCapability.TICK_VOLUME}, MarketStructure.QUOTE_DRIVEN)
BOND = instrument(AssetClass.BOND, "UST10Y", "XNYS", SessionKind.EXCHANGE_HOURS, set(),
                  MarketStructure.QUOTE_DRIVEN)
