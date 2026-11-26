"""T91: anualización y velas por día desde el calendario del instrumento."""
from __future__ import annotations

import importlib.util

import pytest

from eim.instruments.registry import BTCUSDT, SP500
from eim.instruments.timebase import (
    bars_per_day,
    bars_per_year,
    market_days_to_bars,
    sessions_per_year,
)

HOUR = 3_600_000
DAY = 24 * HOUR
XCALS = importlib.util.find_spec("exchange_calendars") is not None


def test_always_keeps_the_historic_8766():
    assert bars_per_year(BTCUSDT, HOUR) == pytest.approx(8766.0)   # backtest/params.py:40
    assert bars_per_year("24/7", DAY) == pytest.approx(365.25)
    assert bars_per_day(BTCUSDT, HOUR) == pytest.approx(24.0)
    assert sessions_per_year(BTCUSDT) == pytest.approx(365.25)
    assert market_days_to_bars(20, BTCUSDT, 4 * HOUR) == 120


def test_rejects_a_non_positive_timeframe():
    with pytest.raises(ValueError):
        bars_per_year(BTCUSDT, 0)


@pytest.mark.skipif(not XCALS, reason="sin el extra `calendars` (exchange_calendars)")
def test_exchange_calendar_counts_sessions_not_hours():
    assert 250 <= bars_per_year(SP500, DAY) <= 253
    assert 250 <= sessions_per_year(SP500) <= 253
    assert bars_per_day(SP500, DAY) == pytest.approx(1.0)
    assert 5.5 <= bars_per_day(SP500, HOUR) <= 7.0            # 6,5 h de sesión
    assert (8766 / bars_per_year(SP500, DAY)) ** 0.5 == pytest.approx(5.9, abs=0.05)  # T87
