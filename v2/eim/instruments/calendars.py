"""Calendarios de mercado (T89): sesiones, festivos, medias jornadas y zona horaria.

Para qué: hasta ahora todo el sistema suponía 24/7, así que un hueco de datos solo podía
significar «falló la captura». Fuera de cripto hay una tercera posibilidad —el mercado
estaba cerrado— y confundirlas es exactamente el «acierto silencioso» que T87 midió. De
aquí salen `is_open`, `next_open` y, sobre todo, `expected_bars`, que es lo que permite a
T90 (`find_gaps`) decir «cerrado» en vez de «sin datos».

**Quién manda.** `24/7` se calcula aquí, sin librería: es una regla exacta y es el camino de
producción (la captura y el bróker simulado corren sobre perpetuos). Todo lo demás lo
contesta `exchange_calendars` 4.13.3 (Apache-2.0, aprobada en la ◆ de T88 §1), siempre con
`start` y `end` explícitos, que es el límite escrito de esa aprobación: su horizonte por
defecto se congela al importar el módulo y los servicios de EIM corren días seguidos.

**Si no está instalada** (va en el extra `calendars`), los calendarios de bolsa levantan
`CalendarUnavailable`. No se adivina: un festivo inventado es peor que una respuesta que
falta, y la propia auditoría de T88 anotó que esos festivos están codificados a mano y sin
cláusula de exactitud. Cualquier festivo que decida algo se contrasta en la fuente.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import TYPE_CHECKING

from eim.core.market import Frozen
from eim.instruments.calendar_specs import (
    ALWAYS,
    CALENDARS,
    FX_WARNINGS,
    NATIVE_SOURCE,
    WEEKDAYS,
    XCALS_SOURCE,
    XCALS_VERSION,
    CalendarSpec,
    CalendarUnavailable,
    Session,
)

__all__ = [
    "ALWAYS", "CALENDARS", "FX_WARNINGS", "NATIVE_SOURCE", "WEEKDAYS", "XCALS_SOURCE",
    "XCALS_VERSION", "Absence", "CalendarSpec", "CalendarUnavailable", "Session", "available",
    "classify_absence", "expected_bars", "is_open", "next_open", "sessions", "spec",
]

if TYPE_CHECKING:
    from eim.instruments.models import Instrument

DAY_MS = 86_400_000
#: Al pedirle el horizonte a `exchange_calendars` se redondea a años enteros, con un año de
#: margen a cada lado. Construir un calendario cuesta ~235 ms, y `find_gaps` barre miles de
#: ventanas: con años enteros, mil ventanas del mismo año construyen UN calendario.
_PAD_YEARS = 1
def spec(calendar: str | Instrument) -> CalendarSpec:
    """Ficha del calendario; acepta un id o un instrumento (usa su `calendar_id`)."""
    cid = calendar if isinstance(calendar, str) else calendar.calendar_id
    try:
        return CALENDARS[cid]
    except KeyError:
        raise CalendarUnavailable(
            f"calendario {cid!r} no registrado (hay: {', '.join(sorted(CALENDARS))})") from None


def _cal_id(calendar: str | Instrument, *, underlying: bool = False) -> str:
    if isinstance(calendar, str):
        return calendar
    cid = calendar.underlying_calendar_id if underlying else calendar.calendar_id
    if cid is None:
        raise CalendarUnavailable(
            f"{calendar.id} no declara calendario del subyacente: no se puede afirmar si estaba "
            "abierto (T88: el contrato no cierra aunque el subyacente sí)")
    return cid


def _xcals(name: str, start_day: str, end_day: str):
    """Calendario de `exchange_calendars` con horizonte EXPLÍCITO (límite escrito de T88).

    Sin caché a propósito: lo que se guarda es el resultado ligero de `_schedule` (dos arrays
    de enteros), no el calendario entero, que pesa megas y no vuelve a hacer falta.
    """
    try:
        import exchange_calendars as xcals
    except ModuleNotFoundError:
        raise CalendarUnavailable(
            f"el calendario {name!r} necesita `exchange_calendars` (extra `calendars`: "
            "pip install -e .[calendars]). No se adivinan festivos.") from None
    return xcals.get_calendar(name, start=start_day, end=end_day)


def _year(ms: int) -> int:
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.UTC).year


@lru_cache(maxsize=16)
def _schedule(name: str, first_year: int, last_year: int):
    """Aperturas y cierres del calendario, en ms epoch UTC y ordenados, como dos arrays.

    Cacheado por años enteros: así barrer un año de ventanas de un día construye el
    calendario una vez, no 365 veces.
    """
    import numpy as np

    sch = _xcals(name, f"{first_year}-01-01", f"{last_year}-12-31").schedule
    cols = []
    for col in ("open", "close"):
        naive = sch[col].dt.tz_convert("UTC").dt.tz_localize(None)
        cols.append(naive.to_numpy(dtype="datetime64[ms]").astype("int64"))
    order = np.argsort(cols[0], kind="stable")
    return cols[0][order], cols[1][order]


def _native_sessions(start: int, end: int) -> list[Session]:
    """24/7: un tramo por día UTC, para que `expected_bars` y las sesiones hablen igual."""
    out = []
    t = (start // DAY_MS) * DAY_MS
    while t < end:
        out.append(Session(t, t + DAY_MS))
        t += DAY_MS
    return out


def sessions(calendar: str | Instrument, start: int, end: int, *,
             underlying: bool = False) -> list[Session]:
    """Sesiones que solapan [start, end), recortadas a esa ventana, en ms epoch UTC.

    Las medias jornadas salen con su cierre real (el viernes después de Acción de Gracias
    cierra a las 18:00 UTC en vez de a las 21:00).
    """
    if end <= start:
        return []
    sp = spec(_cal_id(calendar, underlying=underlying))
    if sp.native:
        raw = _native_sessions(start, end)
    else:
        import numpy as np

        opens, closes = _schedule(str(sp.xcals_name), _year(start) - _PAD_YEARS,
                                  _year(end) + _PAD_YEARS)
        hi = int(np.searchsorted(opens, end, side="left"))
        lo = int(np.searchsorted(closes[:hi], start, side="right"))
        raw = [Session(int(opens[k]), int(closes[k])) for k in range(lo, hi)]
    out = []
    for s in raw:
        lo_t, hi_t = max(s.open_t, start), min(s.close_t, end)
        if hi_t > lo_t:
            out.append(Session(lo_t, hi_t))
    return out


def is_open(calendar: str | Instrument, t: int, *, underlying: bool = False) -> bool:
    """¿Está abierto en ese instante? Para un instrumento, `underlying=True` pregunta por su
    subyacente, que es lo que distingue a un perpetuo TradFi de su bolsa de origen."""
    sp = spec(_cal_id(calendar, underlying=underlying))
    if sp.native:
        return True
    return bool(sessions(calendar, t, t + 1, underlying=underlying))


def next_open(calendar: str | Instrument, t: int, *, horizon_days: int = 30,
              underlying: bool = False) -> int:
    """Primer instante abierto en [t, t + horizon_days). Levanta si no hay ninguno."""
    if is_open(calendar, t, underlying=underlying):
        return t
    found = sessions(calendar, t, t + horizon_days * DAY_MS, underlying=underlying)
    if not found:
        raise CalendarUnavailable(
            f"ninguna sesión de {_cal_id(calendar, underlying=underlying)!r} en los "
            f"{horizon_days} días siguientes a {t}")
    return found[0].open_t


def expected_bars(calendar: str | Instrument, timeframe_ms: int, start: int, end: int, *,
                  underlying: bool = False) -> int:
    """Cuántas velas DEBERÍA haber en [start, end) según el calendario.

    Marcos de un día o más: una vela por sesión (lo que publica cualquier proveedor diario).
    Marcos intradía: las velas alineadas al epoch cuyo inicio cae dentro de una sesión. En
    una sesión que no es múltiplo del marco (6,5 h con velas de 1 h) eso cuenta las alineadas
    y deja fuera el tramo suelto de la apertura: es una cota, y por eso `find_gaps` la usa
    para decidir «cerrado» (0) frente a «sin datos» (> 0), no para cuadrar al dato.
    """
    if timeframe_ms <= 0:
        raise ValueError("timeframe_ms debe ser > 0")
    found = sessions(calendar, start, end, underlying=underlying)
    if timeframe_ms >= DAY_MS:
        if spec(_cal_id(calendar, underlying=underlying)).native:
            return sum(s.ms for s in found) // timeframe_ms
        return len(found)
    total = 0
    for s in found:
        first = -(-s.open_t // timeframe_ms) * timeframe_ms     # primer múltiplo >= apertura
        if first < s.close_t:
            total += (s.close_t - 1 - first) // timeframe_ms + 1
    return total


class Absence(Frozen):
    """Por qué no hay datos en una ventana: porque estaba cerrado, o porque faltan."""

    kind: str                   # "closed" | "missing" | "partial" | "complete"
    calendar_id: str
    expected: int
    observed: int
    source: str
    warnings: tuple[str, ...] = ()

    @property
    def closed(self) -> bool:
        return self.kind == "closed"


def classify_absence(calendar: str | Instrument, timeframe_ms: int, start: int, end: int, *,
                     observed: int = 0, underlying: bool = False) -> Absence:
    """Distingue «cerrado» de «sin datos» para una ventana y un marco.

    `closed`: el calendario no esperaba ninguna vela. `missing`: esperaba y no hay ninguna.
    `partial`: hay menos de las esperadas. `complete`: están todas (o más, si el proveedor
    alinea distinto a la apertura).
    """
    sp = spec(_cal_id(calendar, underlying=underlying))
    exp = expected_bars(calendar, timeframe_ms, start, end, underlying=underlying)
    if exp == 0:
        kind = "closed"
    elif observed <= 0:
        kind = "missing"
    elif observed < exp:
        kind = "partial"
    else:
        kind = "complete"
    return Absence(kind=kind, calendar_id=sp.id, expected=exp, observed=max(observed, 0),
                   source=sp.source, warnings=sp.warnings)


def available() -> dict[str, bool]:
    """Qué calendarios se pueden contestar hoy en este equipo (para avisos de la interfaz)."""
    out = {}
    for cid, sp in CALENDARS.items():
        if sp.native:
            out[cid] = True
            continue
        try:
            sessions(cid, 1_767_225_600_000, 1_767_225_600_000 + DAY_MS)
            out[cid] = True
        except CalendarUnavailable:
            out[cid] = False
    return out
