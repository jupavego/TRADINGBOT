"""Barras por día y por año desde el calendario del instrumento (T91).

Por qué: `bars_per_year = 8766` (`eim/backtest/params.py`) son las horas de un año 24/7; sobre
velas diarias de acciones infla un Sharpe ×5,9 (T87). Aquí la cifra sale del calendario:

- **24/7** (regla propia, exacta): 365,25 días × velas por día. Con 1 h da **8766**, el valor
  de siempre, así que el camino de BTC/ETH no cambia de número.
- **Calendarios de bolsa y 24/5**: velas esperadas por `expected_bars` en un tramo de años
  completos fijo (`REFERENCE_YEARS`), divididas por los años. La NYSE en diario da ≈ 252.

Sin `exchange_calendars` los calendarios de bolsa levantan `CalendarUnavailable` (no se
adivinan festivos). Puro: sin red ni disco. Quién lo usa: T92 (anualización del backtest por
clase) y las ventanas «en días de mercado» de los agentes que las pidan.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache

from eim.instruments.calendars import expected_bars, sessions, spec
from eim.instruments.models import Instrument

DAY_MS = 86_400_000
YEAR_DAYS_ALWAYS = 365.25
#: Años completos (inclusivos) con los que se promedia un calendario de bolsa: fijos para que
#: la cifra sea reproducible y no cambie cada 1 de enero.
REFERENCE_YEARS = (2016, 2025)


def _year_bounds(first: int, last: int) -> tuple[int, int]:
    start = dt.datetime(first, 1, 1, tzinfo=dt.UTC)
    end = dt.datetime(last + 1, 1, 1, tzinfo=dt.UTC)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _cal(calendar: str | Instrument) -> str:
    return calendar if isinstance(calendar, str) else calendar.calendar_id


@lru_cache(maxsize=64)
def _per_year(cal_id: str, timeframe_ms: int, years: tuple[int, int]) -> float:
    if spec(cal_id).native:
        return YEAR_DAYS_ALWAYS * DAY_MS / timeframe_ms
    lo, hi = _year_bounds(*years)
    return expected_bars(cal_id, timeframe_ms, lo, hi) / (years[1] - years[0] + 1)


@lru_cache(maxsize=64)
def _sessions_per_year(cal_id: str, years: tuple[int, int]) -> float:
    if spec(cal_id).native:
        return YEAR_DAYS_ALWAYS
    lo, hi = _year_bounds(*years)
    return len(sessions(cal_id, lo, hi)) / (years[1] - years[0] + 1)


def bars_per_year(calendar: str | Instrument, timeframe_ms: int,
                  years: tuple[int, int] = REFERENCE_YEARS) -> float:
    """Velas de `timeframe_ms` en un año del calendario (para anualizar)."""
    if timeframe_ms <= 0:
        raise ValueError("timeframe_ms debe ser > 0")
    return _per_year(_cal(calendar), timeframe_ms, years)


def sessions_per_year(calendar: str | Instrument,
                      years: tuple[int, int] = REFERENCE_YEARS) -> float:
    """Sesiones (días de mercado) por año: 365,25 en 24/7, ≈ 252 en la NYSE."""
    return _sessions_per_year(_cal(calendar), years)


def bars_per_day(calendar: str | Instrument, timeframe_ms: int,
                 years: tuple[int, int] = REFERENCE_YEARS) -> float:
    """Velas por día DE MERCADO (por sesión): 24 en 24/7 con 1 h, ≈ 6 en la NYSE, 1 en diario."""
    return bars_per_year(calendar, timeframe_ms, years) / sessions_per_year(calendar, years)


def market_days_to_bars(days: float, calendar: str | Instrument, timeframe_ms: int) -> int:
    """Ventana de `days` días de mercado expresada en velas de sesión (al menos 1)."""
    return max(1, round(days * bars_per_day(calendar, timeframe_ms)))
