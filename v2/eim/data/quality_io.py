"""Calidad por dato desde el almacén (T90): huecos según calendario e informe por serie.

La lógica es pura y vive en `eim/data/quality.py`; aquí solo se lee el almacén con DuckDB y
se resuelve el calendario del instrumento. `Store.find_gaps` delega en `gaps_in`, así que
sin calendario el resultado es exactamente el de siempre (la regla 24/7 de antes de T90).
"""

from __future__ import annotations

import duckdb

from eim.data.quality import (
    SeriesQuality,
    assess,
    calendar_gaps,
    calendar_sessions,
    stale_grace,
)
from eim.data.session_bars import closed_before
from eim.data.timeframes import tf_ms
from eim.instruments import calendars
from eim.instruments.calendar_specs import CalendarUnavailable
from eim.instruments.models import DataCapability, Instrument


def raw_gaps(store, symbol: str, timeframe: str, start: int | None = None,
             end: int | None = None, kind: str = "candles") -> list[tuple[int, int]]:
    """Huecos brutos (regla 24/7): (t de la primera vela faltante, t de la última faltante)."""
    step = tf_ms(timeframe)
    src = store.sql_source(kind, symbol, timeframe, start, end)
    if src is None:
        return []
    rows = duckdb.connect().execute(
        f"SELECT t, nxt FROM (SELECT t, lead(t) OVER (ORDER BY t) AS nxt FROM {src}) "
        f"WHERE nxt - t > {step} ORDER BY t").fetchall()
    return [(int(a) + step, int(b) - step) for a, b in rows]


def _cal_id(calendar: str | Instrument, underlying: bool) -> str | None:
    if isinstance(calendar, str):
        return calendar
    return calendar.underlying_calendar_id if underlying else calendar.calendar_id


def is_continuous(calendar: str | Instrument, underlying: bool = False) -> bool:
    """¿Calendario 24/7? (nunca cierra: ningún hueco puede ser un cierre)."""
    cid = _cal_id(calendar, underlying)
    return cid is not None and cid in calendars.CALENDARS and calendars.spec(cid).native


def gaps_in(store, symbol: str, timeframe: str, start: int | None = None,
            end: int | None = None, kind: str = "candles", calendar=None,
            underlying: bool = False) -> list[tuple[int, int]]:
    """Huecos de la serie; con `calendar` (id o instrumento) solo los que tenían mercado abierto.

    Un calendario de bolsa sin `exchange_calendars` instalado levanta `CalendarUnavailable`:
    no se adivina qué días eran festivo.
    """
    raw = raw_gaps(store, symbol, timeframe, start, end, kind)
    if calendar is None or not raw or is_continuous(calendar, underlying):
        return raw
    real, _closed = calendar_gaps(raw, tf_ms(timeframe),
                                  calendar_sessions(calendar, underlying=underlying))
    return real


def duplicates(store, symbol: str, timeframe: str, kind: str = "candles") -> int:
    """Velas repetidas entre el tramo histórico y el vivo (la lectura no las duplica)."""
    src = store.sql_source(kind, symbol, timeframe, dedupe=False)
    if src is None:
        return 0
    n, d = duckdb.connect().execute(f"SELECT count(*), count(DISTINCT t) FROM {src}").fetchone()
    return int(n) - int(d)


def series_quality(store, symbol: str, timeframe: str, *, asof: int,
                   instrument: Instrument | None = None, calendar: str | None = None,
                   kind: str = "candles", delay_ms: int = 0, start: int | None = None,
                   underlying: bool = False) -> SeriesQuality:
    """Informe de calidad de una serie a `asof`, con el calendario del instrumento.

    Sin instrumento se usa `calendar` (por defecto `24/7`) y no se juzga el volumen. Si el
    calendario no se puede contestar en este equipo, el informe lo dice y no inventa nada.
    """
    step = tf_ms(timeframe)
    cal: str | Instrument = instrument if instrument is not None else (calendar or "24/7")
    cid = _cal_id(cal, underlying) or ""
    continuous = is_continuous(cal, underlying)
    sessions = None
    if not continuous:
        try:
            if not cid:
                raise CalendarUnavailable("el instrumento no declara ese calendario")
            sessions = calendar_sessions(cal, underlying=underlying)
            sessions(asof - step, asof)           # prueba barata: ¿hay autoridad aquí?
        except CalendarUnavailable:
            sessions = None
    cut = closed_before(timeframe, asof, sessions)      # solo velas cerradas a `asof`
    src = store.sql_source(kind, symbol, timeframe, start, cut)
    rows = [] if src is None else duckdb.connect().execute(
        f"SELECT t, c, v FROM {src} ORDER BY t").fetchall()
    t = [int(r[0]) for r in rows]
    c = [float(r[1]) for r in rows]
    has_volume = instrument is not None and instrument.has(DataCapability.REAL_VOLUME)
    v = [float(r[2] or 0.0) for r in rows] if has_volume else None
    raw = [g for g in raw_gaps(store, symbol, timeframe, start, cut, kind) if g[1] < cut]
    grace = stale_grace(instrument.asset_class.value if instrument is not None else None)
    return assess(t, c, v, step=step, asof=asof, raw_gaps=raw, sessions=sessions,
                  calendar_id=cid, duplicates=duplicates(store, symbol, timeframe, kind),
                  grace_bars=grace, delay_ms=delay_ms, continuous=continuous)
