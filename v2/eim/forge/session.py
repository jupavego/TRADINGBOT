"""Sesión americana en velas de 5 m (T208): qué vela pertenece a la sesión y cuándo puede operar.

La sesión es la de la bolsa de Nueva York, **no** una franja fija de UTC: `America/New_York`
09:30–16:00, así el horario de verano se resuelve solo (09:30 ET = 13:30 UTC en verano y 14:30 UTC
en invierno; las dos caen en la rejilla de 5 m). Se excluyen fines de semana, festivos de NYSE y
los días de media sesión (cierre a las 13:00 ET), para no mezclar sesiones de distinta longitud.

Todo sale de los tiempos de apertura de las velas (`t`, ms epoch): no hay nada que adivinar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

NY = ZoneInfo("America/New_York")
OPEN_H, OPEN_M = 9, 30
CLOSE_H, CLOSE_M = 16, 0
#: Las señales solo pueden nacer en velas que abren en [09:35, 15:00) ET: la primera vela de la
#: sesión no dispara y después de las 15:00 no se abre nada nuevo.
SIGNAL_FROM = (9, 35)
SIGNAL_UNTIL = (15, 0)

#: Festivos de NYSE (mercado cerrado) 2022-2027. Fuente: calendario público de NYSE.
HOLIDAYS: frozenset[str] = frozenset({
    "2022-11-24", "2022-12-26",
    "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29", "2023-06-19",
    "2023-07-04", "2023-09-04", "2023-11-23", "2023-12-25",
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27", "2024-06-19",
    "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
    "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
    "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
    "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
})
#: Medias sesiones (cierre a las 13:00 ET): el día entero queda fuera.
HALF_DAYS: frozenset[str] = frozenset({
    "2022-11-25", "2023-07-03", "2023-11-24", "2024-07-03", "2024-11-29", "2024-12-24",
    "2025-07-03", "2025-11-28", "2025-12-24", "2026-11-27", "2026-12-24", "2027-11-26",
})


@dataclass(frozen=True)
class Sessions:
    """Máscaras de sesión de una serie de velas (todas con la longitud de la serie).

    - `sid`: índice de sesión de cada vela, −1 fuera de sesión.
    - `can_signal`: la vela puede dar una señal (su entrada cabe en la misma sesión).
    - `last`: índice de la última vela de su sesión (−1 fuera); es el cierre forzoso.
    - `day`: día de sesión (entero creciente) de cada vela, −1 fuera; bloque de los remuestreos.
    - `starts`: índice de la primera vela de cada sesión.
    """

    sid: np.ndarray
    can_signal: np.ndarray
    last: np.ndarray
    day: np.ndarray
    starts: np.ndarray
    dates: tuple[str, ...]


def _ms(d: date, hh: int, mm: int) -> int:
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).timestamp() * 1000)


def trading_dates(t0_ms: int, t1_ms: int) -> list[date]:
    """Días con sesión americana completa entre dos instantes (ms epoch, inclusive)."""
    d0 = datetime.fromtimestamp(t0_ms / 1000, NY).date() - timedelta(days=1)
    d1 = datetime.fromtimestamp(t1_ms / 1000, NY).date() + timedelta(days=1)
    out, d = [], d0
    while d <= d1:
        iso = d.isoformat()
        if d.weekday() < 5 and iso not in HOLIDAYS and iso not in HALF_DAYS:
            out.append(d)
        d += timedelta(days=1)
    return out


def build(t: np.ndarray) -> Sessions:
    """Máscaras de sesión de las velas que abren en `t` (ms epoch, ordenados)."""
    n = len(t)
    sid = np.full(n, -1, dtype=np.int32)
    can = np.zeros(n, dtype=bool)
    last = np.full(n, -1, dtype=np.int32)
    if n == 0:
        return Sessions(sid, can, last, sid.copy(), np.empty(0, np.int32), ())
    days = trading_dates(int(t[0]), int(t[-1]))
    kept: list[str] = []
    starts: list[int] = []
    for d in days:
        a = _ms(d, OPEN_H, OPEN_M)
        b = _ms(d, CLOSE_H, CLOSE_M)
        i0, i1 = int(np.searchsorted(t, a, "left")), int(np.searchsorted(t, b, "left"))
        if i1 - i0 < 2:          # sesión sin velas suficientes en la serie: no cuenta
            continue
        k = len(kept)
        sid[i0:i1] = k
        last[i0:i1] = i1 - 1
        sa, sb = _ms(d, *SIGNAL_FROM), _ms(d, *SIGNAL_UNTIL)
        j0, j1 = int(np.searchsorted(t, sa, "left")), int(np.searchsorted(t, sb, "left"))
        can[j0:j1] = True
        kept.append(d.isoformat())
        starts.append(i0)
    # una señal necesita que su vela de entrada (la siguiente) siga en la MISMA sesión
    nxt_same = np.zeros(n, dtype=bool)
    nxt_same[:-1] = sid[1:] == sid[:-1]
    can &= nxt_same & (sid >= 0)
    return Sessions(sid, can, last, sid.copy(), np.asarray(starts, np.int32), tuple(kept))
