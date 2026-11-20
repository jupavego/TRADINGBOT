"""Registro universal de instrumentos y calendarios (T89).

Un instrumento nuevo **se registra, no se codifica**: la semilla está en `registry.py`, el
descubrimiento en `discovery.py` (funciones puras) y su historia en
`eim/data/instruments_store.py` (DuckDB). Los calendarios de sesiones y festivos, en
`calendars.py`.
"""

from eim.instruments.calendars import (
    ALWAYS,
    CALENDARS,
    WEEKDAYS,
    Absence,
    CalendarSpec,
    CalendarUnavailable,
    Session,
    classify_absence,
    expected_bars,
    is_open,
    next_open,
    sessions,
)
from eim.instruments.models import (
    ID_RE,
    SCHEMA_VERSION,
    AssetClass,
    DataCapability,
    EventKind,
    Instrument,
    InstrumentEvent,
    InstrumentStatus,
    MarketStructure,
    SessionKind,
    TradableLevel,
    make_id,
)

__all__ = [
    "ALWAYS", "CALENDARS", "ID_RE", "SCHEMA_VERSION", "WEEKDAYS", "Absence", "AssetClass",
    "CalendarSpec", "CalendarUnavailable", "DataCapability", "EventKind", "Instrument",
    "InstrumentEvent", "InstrumentStatus", "MarketStructure", "Session", "SessionKind",
    "TradableLevel", "classify_absence", "expected_bars", "is_open", "make_id", "next_open",
    "sessions",
]
