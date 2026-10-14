"""Evento del calendario económico (T36). I/O en `data/providers/calendar.py`."""

from __future__ import annotations

from typing import Literal

from eim.core.market import Frozen

Impact = Literal["bajo", "medio", "alto"]


class EconEvent(Frozen):
    """Publicación macro o cripto programada; todo tiempo en ms epoch UTC.

    `previous`/`forecast`/`actual`/`revised` son None cuando la fuente no los da: las fuentes
    oficiales gratuitas no publican consenso, así que `forecast` es None (nunca se inventa).
    `revised` = valor revisado del periodo anterior (si difiere de `previous`).
    `fetched_at` = última consulta correcta de la fuente que confirmó el evento (point-in-time).
    """

    id: str  # estable: "<fuente>:<nombre>:<AAAAMMDD>"
    t_utc: int
    name: str
    country: str  # "US", "CRYPTO"
    impact: Impact
    previous: float | None = None
    forecast: float | None = None
    actual: float | None = None
    revised: float | None = None
    unit: str = ""  # unidad de los valores ("IPC general m/m %"); vacío si no hay valores
    source: str
    fetched_at: int
