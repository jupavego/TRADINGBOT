"""Calendario económico en el almacén: historial point-in-time, ventana del snapshot y
vencimientos trimestrales de Binance (regla). Sin red: el I/O de red vive en `providers/`.

`root/calendar/events.parquet` es de solo añadir: cada cambio de un evento (hora, valores,
cancelación) es una fila nueva con `seen_at` = consulta en la que se vio; nada se sobrescribe,
así un valor revisado convive con el original. `fetches.parquet` registra cada consulta por
fuente (correcta o fallida). Leer "a `asof`" = solo filas con `seen_at`/`fetched_at` ≤ `asof`.
"""

from __future__ import annotations

import calendar as _cal
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from eim.core import EconEvent
from eim.data.providers.calendar import SOURCES

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
BEFORE_MS = DAY_MS          # ventana del snapshot: −24 h …
AFTER_MS = 7 * DAY_MS       # … +7 d
EXPIRY_SRC = "binance_expiry"
EXPIRY_LABEL = ("regla: vencimiento trimestral USDⓈ-M de Binance (último viernes de "
                "mar/jun/sep/dic, 08:00 UTC; verificado con exchangeInfo 2026-10-14)")

_FIELDS = ("t_utc", "name", "country", "impact", "previous", "forecast", "actual", "revised",
           "unit", "source")
_EV = ("id VARCHAR, seen_at BIGINT, t_utc BIGINT, name VARCHAR, country VARCHAR, "
       "impact VARCHAR, previous DOUBLE, forecast DOUBLE, actual DOUBLE, revised DOUBLE, "
       "unit VARCHAR, source VARCHAR, src VARCHAR, cancelled BOOLEAN")
_FETCH = "src VARCHAR, fetched_at BIGINT, ok BOOLEAN, n BIGINT, t_first BIGINT, t_last BIGINT"


def _lit(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


def quarterly_expiries(lo: int, hi: int, fetched_at: int) -> list[EconEvent]:
    """Vencimientos de futuros trimestrales en [lo, hi]: último viernes del trimestre 08:00."""
    out = []
    y0 = datetime.fromtimestamp(lo / 1000, tz=UTC).year
    for y in (y0, y0 + 1):
        for mo in (3, 6, 9, 12):
            last = _cal.monthrange(y, mo)[1]
            d = max(day for day in range(last - 6, last + 1) if _cal.weekday(y, mo, day) == 4)
            t = int(datetime(y, mo, d, 8, tzinfo=UTC).timestamp() * 1000)
            if lo <= t <= hi:
                out.append(EconEvent(
                    id=f"{EXPIRY_SRC}:quarterly:{y}{mo:02d}{d:02d}", t_utc=t,
                    name="Vencimiento futuros trimestrales Binance (BTC/ETH)", country="CRYPTO",
                    impact="medio", source=EXPIRY_LABEL, fetched_at=fetched_at))
    return out


class CalendarStore:
    def __init__(self, data_root: str | Path) -> None:
        self.dir = Path(data_root) / "calendar"

    # --- parquet ----------------------------------------------------------
    def _read(self, name: str) -> list[tuple]:
        f = self.dir / f"{name}.parquet"
        if not f.exists():
            return []
        return duckdb.connect().execute(
            f"SELECT * FROM read_parquet({_lit(f)}, hive_partitioning=false)").fetchall()

    def _write(self, name: str, schema: str, rows: list[tuple]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        f, tmp = self.dir / f"{name}.parquet", self.dir / f"{name}.tmp"
        con = duckdb.connect()
        con.execute(f"CREATE TABLE t ({schema})")
        if rows:
            con.executemany(f"INSERT INTO t VALUES ({', '.join('?' * len(rows[0]))})", rows)
        con.execute(f"COPY t TO {_lit(tmp)} (FORMAT PARQUET)")
        con.close()
        for attempt in range(5):  # Windows: falla si un lector tiene el archivo abierto
            try:
                tmp.replace(f)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)

    # --- escritura ----------------------------------------------------------
    @staticmethod
    def _key(row: tuple) -> tuple:
        return row[2:12] + (row[13],)

    def _latest(self, rows: list[tuple], asof: int | None = None) -> dict[str, tuple]:
        best: dict[str, tuple] = {}
        for r in rows:
            if (asof is None or r[1] <= asof) and (r[0] not in best or r[1] >= best[r[0]][1]):
                best[r[0]] = r
        return best

    def record(self, src: str, events: list[EconEvent] | None, fetched_at: int) -> dict:
        """Registra una consulta. None = fuente caída (no toca los eventos). Los eventos futuros
        que desaparecen de una consulta correcta se marcan cancelados (fila nueva)."""
        fetches = self._read("fetches")
        ts = [e.t_utc for e in events or []]
        fetches.append((src, fetched_at, events is not None, len(ts),
                        min(ts) if ts else None, max(ts) if ts else None))
        added = cancelled = 0
        if events is not None:
            rows = self._read("events")
            latest = self._latest([r for r in rows if r[12] == src])
            seen = set()
            for e in events:
                seen.add(e.id)
                row = (e.id, fetched_at, *(getattr(e, k) for k in _FIELDS), src, False)
                old = latest.get(e.id)
                if old is None or self._key(old) != self._key(row):
                    rows.append(row)
                    added += 1
            for eid, old in latest.items():
                if eid not in seen and not old[13] and old[2] > fetched_at:
                    rows.append((*old[:1], fetched_at, *old[2:13], True))
                    cancelled += 1
            if added or cancelled:
                self._write("events", _EV, rows)
        self._write("fetches", _FETCH, fetches)
        return {"source": src, "ok": events is not None, "events": len(ts), "changed": added,
                "cancelled": cancelled}

    def update_values(self, event_id: str, values: dict, seen_at: int) -> bool:
        """Nueva versión con valores publicados (FRED); la versión previa se conserva."""
        rows = self._read("events")
        old = self._latest(rows).get(event_id)
        if old is None:
            return False
        cur = dict(zip(_FIELDS, old[2:12], strict=True))
        new = cur | {k: values[k] for k in ("actual", "previous", "revised", "unit")
                     if k in values}
        if new == cur:
            return False
        rows.append((event_id, seen_at, *(new[k] for k in _FIELDS), old[12], old[13]))
        self._write("events", _EV, rows)
        return True

    # --- lectura point-in-time ---------------------------------------------
    def last_fetches(self, asof: int) -> dict[str, tuple[int, int | None, int | None]]:
        """{fuente: (fetched_at, t_first, t_last)} de la última consulta correcta ≤ asof."""
        out: dict[str, tuple[int, int | None, int | None]] = {}
        for src, t, ok, _n, t0, t1 in self._read("fetches"):
            if ok and t <= asof and (src not in out or t >= out[src][0]):
                out[src] = (t, t0, t1)
        return out

    def last_attempt(self) -> dict[str, tuple[int, bool]]:
        out: dict[str, tuple[int, bool]] = {}
        for src, t, ok, *_ in self._read("fetches"):
            if src not in out or t >= out[src][0]:
                out[src] = (t, bool(ok))
        return out

    def versions(self, event_id: str) -> list[tuple]:
        return sorted((r for r in self._read("events") if r[0] == event_id), key=lambda r: r[1])

    def window(self, asof: int, before: int = BEFORE_MS, after: int = AFTER_MS):
        """(eventos, sources, coverage) conocidos a `asof` en [asof−before, asof+after];
        None si a esa fecha nunca hubo una consulta correcta."""
        fetched = self.last_fetches(asof)
        if not fetched:
            return None
        lo, hi = asof - before, asof + after
        events = []
        for r in self._latest(self._read("events"), asof).values():
            src = r[12]
            if r[13] or src not in fetched or not lo <= r[2] <= hi:
                continue
            events.append(EconEvent(id=r[0], fetched_at=fetched[src][0],
                                    **dict(zip(_FIELDS, r[2:12], strict=True))))
        events += quarterly_expiries(lo, hi, asof)
        sources = {"events": ", ".join(sorted([*fetched, EXPIRY_SRC]))}
        coverage: dict[str, tuple[int, int]] = {}
        for src, (t, _t0, t1) in fetched.items():
            sources[f"events:{src}"] = SOURCES.get(src, src)
            coverage[f"events:{src}"] = (t, t1 if t1 is not None else t)
        sources[f"events:{EXPIRY_SRC}"] = EXPIRY_LABEL
        coverage[f"events:{EXPIRY_SRC}"] = (asof, hi)
        horizon = min([hi, *(t1 for _, _, t1 in fetched.values() if t1 is not None)])
        coverage["events"] = (lo, max(lo, horizon))
        return sorted(events, key=lambda e: (e.t_utc, e.id)), sources, coverage


def read_calendar(data_root: str | Path, asof: int):
    """Ventana del snapshot; un fallo de lectura (archivo en reemplazo) se trata como ausente."""
    try:
        return CalendarStore(data_root).window(asof)
    except (duckdb.Error, OSError):
        return None
