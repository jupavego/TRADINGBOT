"""Qué calendarios existen y quién los contesta (T89).

Separado de `calendars.py` para que el registro de calendarios (datos) y el cálculo de
sesiones (lógica) se lean por separado y ninguno de los dos pase de 300 líneas.

Añadir un calendario de bolsa = una fila en `CALENDARS` con su nombre en `exchange_calendars`
(103 disponibles). **Nunca una tabla de festivos escrita a mano**: la auditoría de T88 anotó
que los de la librería ya están codificados a mano y sin cláusula de exactitud, así que
duplicarlos aquí solo añadiría una fuente más que nadie contrasta.
"""

from __future__ import annotations

from typing import NamedTuple

from pydantic import field_validator

from eim.core.market import Frozen

XCALS_VERSION = "4.13.3"
XCALS_SOURCE = f"exchange_calendars {XCALS_VERSION} (Apache-2.0; ◆ T88 §1)"
NATIVE_SOURCE = "eim.instruments.calendars (regla propia, exacta)"

#: Aviso que acompaña a `24/5`: es una convención de días hábiles, no un calendario real.
FX_WARNINGS = (
    "`24/5` no conoce festivos: Viernes Santo o Navidad en día hábil salen como abiertos.",
    "La semana real del FX al contado abre el domingo a las 22:00 UTC y cierra el viernes a "
    "las 22:00 UTC; `24/5` la aproxima a días UTC completos de lunes a viernes.",
)


class CalendarUnavailable(RuntimeError):
    """No hay autoridad para ese calendario (falta el extra `calendars`, o el id no existe)."""


class Session(NamedTuple):
    """Una sesión, en ms epoch UTC; `close_t` es exclusivo."""

    open_t: int
    close_t: int

    @property
    def ms(self) -> int:
        return self.close_t - self.open_t


class CalendarSpec(Frozen):
    """Ficha de un calendario: quién lo contesta y con qué salvedades."""

    id: str
    label: str
    tz: str
    native: bool = False          # True = se calcula aquí, sin librería
    xcals_name: str | None = None
    source: str
    warnings: tuple[str, ...] = ()

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("el id del calendario no puede estar vacío")
        return v


ALWAYS = "24/7"
WEEKDAYS = "24/5"

#: Calendarios registrados (ver el encabezado del módulo para añadir uno).
CALENDARS: dict[str, CalendarSpec] = {
    ALWAYS: CalendarSpec(
        id=ALWAYS, label="Continuo, 24/7 (cripto)", tz="UTC", native=True, source=NATIVE_SOURCE),
    WEEKDAYS: CalendarSpec(
        id=WEEKDAYS, label="Días hábiles completos, 24/5 (FX al contado)", tz="UTC",
        xcals_name="24/5", source=XCALS_SOURCE, warnings=FX_WARNINGS),
    "XNYS": CalendarSpec(
        id="XNYS", label="Bolsa de Nueva York", tz="America/New_York", xcals_name="XNYS",
        source=XCALS_SOURCE),
    "XNAS": CalendarSpec(
        id="XNAS", label="Nasdaq", tz="America/New_York", xcals_name="XNAS",
        source=XCALS_SOURCE),
    "CMES": CalendarSpec(
        id="CMES", label="CME (futuros)", tz="America/Chicago", xcals_name="CMES",
        source=XCALS_SOURCE),
    "IEPA": CalendarSpec(
        id="IEPA", label="ICE Futures US", tz="America/New_York", xcals_name="IEPA",
        source=XCALS_SOURCE),
    "XLON": CalendarSpec(
        id="XLON", label="Bolsa de Londres", tz="Europe/London", xcals_name="XLON",
        source=XCALS_SOURCE),
    "XETR": CalendarSpec(
        id="XETR", label="Xetra (Fráncfort)", tz="Europe/Berlin", xcals_name="XETR",
        source=XCALS_SOURCE),
}


