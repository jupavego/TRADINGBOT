"""Catálogo de instrumentos en DuckDB (T89): `data/instruments.duckdb`.

Base aparte de `reports.duckdb` por la misma razón que las demás: quien descubre instrumentos
corre en su propio proceso y DuckDB no admite dos procesos escribiendo el mismo archivo.

Guarda tres cosas:

- **`instruments`**: la ficha vigente de cada instrumento (una fila por `id`).
- **`instrument_events`**: su historia fechada — altas, bajas, vencimientos, suspensiones y
  cambios de contrato. La clave primaria `(instrument_id, kind, t)` hace que repetir un
  descubrimiento no duplique hechos.
- **`instrument_aliases`**: el símbolo legado que resuelve a un instrumento, para que
  `BTCUSDT` o `SP500` sigan siendo identificadores válidos (requisito 4 de T89).

`upsert` es idempotente: con la misma entrada no cambia nada y lo dice (`unchanged`). El
descubrimiento se puede correr cada hora sin inflar la historia.

Línea de órdenes en `eim/instruments/__main__.py` (`python -m eim.instruments --help`).
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

import duckdb

from eim.data.duck import tune
from eim.instruments import discovery
from eim.instruments.models import (
    SCHEMA_VERSION,
    AssetClass,
    DataCapability,
    Instrument,
    InstrumentEvent,
    InstrumentStatus,
    TradableLevel,
)

DB_NAME = "instruments.duckdb"
_DDL = """
CREATE TABLE IF NOT EXISTS instruments (
    id VARCHAR PRIMARY KEY, schema_version VARCHAR, symbol VARCHAR, label VARCHAR,
    asset_class VARCHAR, market_structure VARCHAR, venue VARCHAR, status VARCHAR,
    currency VARCHAR, quote_currency VARCHAR, calendar_id VARCHAR,
    underlying_calendar_id VARCHAR, session VARCHAR, tick DOUBLE, lot DOUBLE,
    multiplier DOUBLE, min_notional DOUBLE, expiry BIGINT, underlying VARCHAR,
    tradable_level INTEGER, data_capabilities VARCHAR, aliases VARCHAR, listed_at BIGINT,
    source VARCHAR, first_seen BIGINT, updated_at BIGINT);
CREATE TABLE IF NOT EXISTS instrument_events (
    instrument_id VARCHAR, kind VARCHAR, t BIGINT, detail VARCHAR, source VARCHAR,
    observed_at BIGINT, PRIMARY KEY (instrument_id, kind, t));
CREATE TABLE IF NOT EXISTS instrument_aliases (
    alias VARCHAR PRIMARY KEY, instrument_id VARCHAR, added_at BIGINT);
"""
_COLS = ("id", "schema_version", "symbol", "label", "asset_class", "market_structure", "venue",
         "status", "currency", "quote_currency", "calendar_id", "underlying_calendar_id",
         "session", "tick", "lot", "multiplier", "min_notional", "expiry", "underlying",
         "tradable_level", "data_capabilities", "aliases", "listed_at", "source")


def _row(inst: Instrument) -> tuple:
    return (
        inst.id, inst.schema_version, inst.symbol, inst.label, inst.asset_class.value,
        inst.market_structure.value, inst.venue, inst.status.value, inst.currency,
        inst.quote_currency, inst.calendar_id, inst.underlying_calendar_id, inst.session.value,
        inst.tick, inst.lot, inst.multiplier, inst.min_notional, inst.expiry, inst.underlying,
        int(inst.tradable_level),
        json.dumps(sorted(c.value for c in inst.data_capabilities)),
        json.dumps(list(inst.aliases)), inst.listed_at, inst.source)


def _instrument(row: Sequence) -> Instrument:
    d = dict(zip(_COLS, row, strict=True))
    caps = json.loads(d["data_capabilities"])
    d["data_capabilities"] = frozenset(DataCapability(c) for c in caps)
    d["aliases"] = tuple(json.loads(d["aliases"]))
    d["tradable_level"] = TradableLevel(int(d["tradable_level"]))
    return Instrument(**d)


class AmbiguousKey(LookupError):
    """Un símbolo o alias que apunta a más de un instrumento: hay que pedirlo por su id."""


class Upserted:
    """Qué hizo un `upsert`: cuántos entraron nuevos, cuántos cambiaron y cuántos no."""

    __slots__ = ("added", "changed", "unchanged", "events")

    def __init__(self, added: int = 0, changed: int = 0, unchanged: int = 0,
                 events: int = 0) -> None:
        self.added, self.changed, self.unchanged, self.events = added, changed, unchanged, events

    def as_json(self) -> dict[str, int]:
        return {"added": self.added, "changed": self.changed, "unchanged": self.unchanged,
                "events": self.events}

    def __repr__(self) -> str:
        return f"Upserted({self.as_json()})"


class InstrumentsStore:
    """Catálogo de instrumentos y su historia fechada."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(self._path)
        tune(self._con)
        self._con.execute(_DDL)
        self._lock = threading.Lock()

    def close(self) -> None:
        self._con.close()

    # --- lectura ----------------------------------------------------------
    def get(self, key: str) -> Instrument | None:
        """Ficha por id, símbolo nativo o alias legado (en ese orden).

        Si un símbolo o alias apunta a más de un instrumento, levanta `AmbiguousKey` en vez de
        elegir uno: devolver el oro cuando se pedía la acción sería un error silencioso, y es
        justo lo que la fase 17 tiene que dejar de hacer. Con el id completo nunca hay duda.
        """
        with self._lock:
            row = self._con.execute(
                f"SELECT {', '.join(_COLS)} FROM instruments WHERE id = ?", [key]).fetchone()
            if row is not None:
                return _instrument(row)
            rows = self._con.execute(
                f"SELECT {', '.join(_COLS)} FROM instruments WHERE symbol = ? ORDER BY id",
                [key]).fetchall()
            if not rows:
                rows = self._con.execute(
                    f"SELECT {', '.join('i.' + c for c in _COLS)} FROM instrument_aliases a "
                    "JOIN instruments i ON i.id = a.instrument_id WHERE a.alias = ? "
                    "ORDER BY i.id", [key]).fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            raise AmbiguousKey(
                f"{key!r} apunta a {len(rows)} instrumentos "
                f"({', '.join(str(r[0]) for r in rows)}): pídelo por su id")
        return _instrument(rows[0])

    def resolve(self, key: str) -> Instrument:
        """Como `get`, pero levanta si no está: nada debe seguir con un símbolo desconocido."""
        inst = self.get(key)
        if inst is None:
            raise KeyError(f"instrumento {key!r} no está en el catálogo "
                           f"({self.count()} fichas en {self._path})")
        return inst

    def list(self, *, asset_class: AssetClass | str | None = None,
             status: InstrumentStatus | str | None = None, venue: str | None = None,
             calendar_id: str | None = None, min_level: int | None = None,
             limit: int | None = None) -> list[Instrument]:
        """Fichas que cumplen los filtros, por id.

        `min_level` es el permiso MÍNIMO que se exige (2 = operativa): así una tarea que no
        puede publicar un veredicto sobre datos de nivel 1 lo pide en la consulta y no se
        acuerda de filtrarlo después.
        """
        where, params = [], []
        for col, val in (("asset_class", asset_class), ("status", status), ("venue", venue),
                         ("calendar_id", calendar_id)):
            if val is not None:
                where.append(f"{col} = ?")
                params.append(str(getattr(val, "value", val)))
        if min_level is not None:
            where.append("tradable_level >= ?")
            params.append(int(min_level))
        q = f"SELECT {', '.join(_COLS)} FROM instruments"
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY id"
        if limit is not None:
            q += f" LIMIT {int(limit)}"
        with self._lock:
            rows = self._con.execute(q, params).fetchall()
        return [_instrument(r) for r in rows]

    def symbols(self, **filters) -> tuple[str, ...]:
        """Símbolos nativos de las fichas que cumplen los filtros de `list`."""
        return tuple(i.symbol for i in self.list(**filters))

    def count(self) -> int:
        with self._lock:
            return int(self._con.execute("SELECT count(*) FROM instruments").fetchone()[0])

    def by_status(self) -> dict[str, int]:
        """Cuántas fichas hay de cada estado (el sesgo de supervivencia, a la vista)."""
        with self._lock:
            rows = self._con.execute(
                "SELECT status, count(*) FROM instruments GROUP BY status ORDER BY status"
            ).fetchall()
        return {str(s): int(n) for s, n in rows}

    def events(self, instrument_id: str | None = None, *,
               limit: int | None = None) -> list[InstrumentEvent]:
        q = ("SELECT instrument_id, kind, t, detail, source, observed_at FROM instrument_events"
             + (" WHERE instrument_id = ?" if instrument_id else "")
             + " ORDER BY t, instrument_id, kind")
        if limit is not None:
            q += f" LIMIT {int(limit)}"
        with self._lock:
            rows = self._con.execute(q, [instrument_id] if instrument_id else []).fetchall()
        return [InstrumentEvent(instrument_id=r[0], kind=r[1], t=int(r[2]), detail=r[3] or "",
                                source=r[4] or "", observed_at=r[5]) for r in rows]

    # --- escritura --------------------------------------------------------
    def upsert(self, instruments: Iterable[Instrument], *, t: int | None = None,
               record_events: bool = True) -> Upserted:
        """Guarda fichas y fecha lo que cambió. Idempotente: repetir no altera nada."""
        now = int(time.time() * 1000) if t is None else int(t)
        res, events = Upserted(), []
        for inst in instruments:
            if inst.schema_version != SCHEMA_VERSION:
                raise ValueError(
                    f"{inst.id}: schema_version {inst.schema_version!r} ≠ {SCHEMA_VERSION!r}")
            previous = self.get(inst.id)
            if previous == inst:
                res.unchanged += 1
                continue
            if record_events:
                events += discovery.diff_events(previous, inst, t=now)
            with self._lock:
                seen = self._con.execute(
                    "SELECT first_seen FROM instruments WHERE id = ?", [inst.id]).fetchone()
                first_seen = int(seen[0]) if seen and seen[0] is not None else now
                self._con.execute(
                    f"INSERT OR REPLACE INTO instruments ({', '.join(_COLS)}, first_seen, "
                    "updated_at) VALUES (" + ",".join("?" * (len(_COLS) + 2)) + ")",
                    [*_row(inst), first_seen, now])
                for alias in inst.aliases:
                    dueno = self._con.execute(
                        "SELECT instrument_id FROM instrument_aliases WHERE alias = ?",
                        [alias]).fetchone()
                    if dueno is not None and str(dueno[0]) != inst.id:
                        raise AmbiguousKey(
                            f"el alias {alias!r} ya es de {dueno[0]}: no puede ser también de "
                            f"{inst.id} (un alias legado resuelve a un solo instrumento)")
                    self._con.execute(
                        "INSERT OR REPLACE INTO instrument_aliases VALUES (?,?,?)",
                        [alias, inst.id, now])
            if previous is None:
                res.added += 1
            else:
                res.changed += 1
        res.events = self.add_events(events)
        return res

    def add_events(self, events: Iterable[InstrumentEvent]) -> int:
        """Añade hechos sin duplicar `(instrumento, tipo, t)`. Devuelve cuántos entraron."""
        rows = [(e.instrument_id, e.kind.value, e.t, e.detail, e.source,
                 e.observed_at if e.observed_at is not None else e.t) for e in events]
        if not rows:
            return 0
        with self._lock:
            before = int(self._con.execute("SELECT count(*) FROM instrument_events").fetchone()[0])
            self._con.executemany(
                "INSERT OR IGNORE INTO instrument_events VALUES (?,?,?,?,?,?)", rows)
            after = int(self._con.execute("SELECT count(*) FROM instrument_events").fetchone()[0])
        return after - before

    def sync(self, instruments: Sequence[Instrument], *, t: int | None = None,
             scope: dict | None = None) -> Upserted:
        """`upsert` más las bajas: lo que el catálogo tenía en ese ámbito y la fuente ya no lista.

        `scope` son filtros de `list` que delimitan lo que esa fuente cubre (por ejemplo
        `{"venue": "binance"}`); sin él no se anota ninguna baja, porque un listado parcial no
        autoriza a dar por retirado lo que no venía en él.
        """
        now = int(time.time() * 1000) if t is None else int(t)
        res = self.upsert(instruments, t=now)
        if scope is not None:
            gone = discovery.missing_from(self.list(**scope), instruments, t=now)
            res.events += self.add_events(gone)
        return res


def open_store(data_dir: str | Path) -> InstrumentsStore:
    """Catálogo de un directorio de datos (`<data_dir>/instruments.duckdb`)."""
    return InstrumentsStore(Path(data_dir) / DB_NAME)
