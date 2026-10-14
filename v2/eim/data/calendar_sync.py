"""Sincronización del calendario: fuentes oficiales → almacén point-in-time (+ valores FRED)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path

from eim.data.calendar import DAY_MS, CalendarStore
from eim.data.providers.calendar import PARSERS, OfficialCalendar
from eim.data.providers.fred import SERIES, FredValues

log = logging.getLogger(__name__)
VALUES_LOOKBACK_MS = 3 * DAY_MS   # se buscan valores de publicaciones de los últimos 3 días
VALUES_DELAY_MS = 10 * 60_000     # y que salieron hace ≥10 min (FRED tarda en reflejarlas)


def sync_calendar(store: CalendarStore, provider: OfficialCalendar, now: int,
                  fred: FredValues | None = None) -> dict:
    """Consulta cada fuente y registra el resultado (también los fallos); luego, con clave FRED,
    completa real/anterior/revisado de las publicaciones recientes sin valor."""
    out = {"sources": [store.record(src, provider.fetch(src, now), now) for src in PARSERS],
           "values": 0}
    if fred is None or not fred.enabled:
        return out
    win = store.window(now, before=VALUES_LOOKBACK_MS, after=0)
    for e in (win[0] if win else []):
        if (e.name in SERIES and e.actual is None
                and now - VALUES_LOOKBACK_MS <= e.t_utc <= now - VALUES_DELAY_MS):
            vals = fred.values(e.name, e.t_utc)
            if vals and store.update_values(e.id, vals, now):
                out["values"] += 1
    return out


class CalendarSync:
    """Refresco periódico dentro de la API (hilo aparte para no bloquear el bucle)."""

    def __init__(self, data_root: Path, provider: OfficialCalendar | None = None,
                 fred: FredValues | None = None, interval_s: float = 6 * 3600,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        self.store = CalendarStore(data_root)
        self.provider = provider or OfficialCalendar()
        self.fred = fred if fred is not None else FredValues()
        self.interval_s, self.clock = interval_s, clock
        self.last: dict | None = None

    def run_once(self) -> dict:
        self.last = sync_calendar(self.store, self.provider, self.clock(), self.fred)
        return self.last

    async def loop(self) -> None:
        while True:
            try:
                res = await asyncio.to_thread(self.run_once)
                log.info("calendario sincronizado: %s", res)
            except Exception:  # noqa: BLE001 - el calendario nunca tumba la API
                log.exception("sincronización del calendario fallida")
            await asyncio.sleep(self.interval_s)
