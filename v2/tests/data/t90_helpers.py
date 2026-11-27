"""Fixtures de T90 (`tests/fixtures/t90/`) e instrumentos de prueba, sin red."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

from eim.core import Candle
from eim.data.adjust import PriceEvent
from eim.instruments.calendar_specs import Session
from eim.instruments.models import (
    AssetClass,
    DataCapability,
    Instrument,
    MarketStructure,
    SessionKind,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "t90"
DAY = 86_400_000
HOUR = 3_600_000

#: Los calendarios de bolsa y el `24/5` necesitan el extra `calendars` (◆ T88 §1).
needs_xcals = pytest.mark.skipif(
    importlib.util.find_spec("exchange_calendars") is None,
    reason="calendarios de bolsa: extra `calendars` (◆ T88 §1)")


def ms(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso).replace(tzinfo=dt.UTC).timestamp() * 1000)


def load(name: str) -> dict:
    d = json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))
    d["candles"] = [Candle(t=r[0], o=r[1], h=r[2], l=r[3], c=r[4], v=r[5]) for r in d["candles"]]
    d["events"] = [PriceEvent(**e) for e in d.get("events", [])]
    return d


def weekdays(start: int, end: int) -> list[Session]:
    """Sesiones de lunes a viernes, días UTC completos (la convención `24/5`, sin librería)."""
    out, t = [], start - start % DAY
    while t < end:
        if dt.datetime.fromtimestamp(t / 1000, tz=dt.UTC).weekday() < 5:
            s = Session(max(t, start), min(t + DAY, end))
            if s.close_t > s.open_t:
                out.append(s)
        t += DAY
    return out


def instrument(symbol: str, asset_class: AssetClass, calendar: str, *,
               volume: bool = True, structure: MarketStructure = MarketStructure.CONTINUOUS_BOOK,
               session: SessionKind = SessionKind.EXCHANGE_HOURS) -> Instrument:
    caps = {DataCapability.CANDLES} | ({DataCapability.REAL_VOLUME} if volume else set())
    return Instrument(
        id=f"{asset_class.value}.test.{symbol}", symbol=symbol, label=f"{symbol} (prueba T90)",
        asset_class=asset_class, market_structure=structure, venue="test", currency="USD",
        quote_currency="USD", calendar_id=calendar, underlying_calendar_id=calendar,
        session=session, data_capabilities=frozenset(caps), source="fixture T90")


ACME = instrument("ACME", AssetClass.EQUITY, "XNYS")
EURUSD = instrument("EURUSD", AssetClass.FX, "24/5", volume=False,
                    structure=MarketStructure.QUOTE_DRIVEN, session=SessionKind.WEEKDAYS)
CLX = instrument("CLX", AssetClass.FUTURE, "24/7", session=SessionKind.ALWAYS)
#: Una acción con calendario 24/7, para probar ajuste y marcas en equipos sin el extra.
ACME_247 = instrument("ACME", AssetClass.EQUITY, "24/7", session=SessionKind.ALWAYS)
