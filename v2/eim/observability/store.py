"""Almacén del observatorio (T73): `obs.duckdb`, archivo propio y DERIVADO de los JSONL.

Guarda lo necesario para reconstruir qué pasó, con qué datos y por qué; no copia snapshots ni
datos de mercado (solo referencias y hashes) ni duplica los libros de riesgo, simulación o
reportes. Un solo escritor (el indexador dentro de la API) bajo un cerrojo; las consultas de la
API comparten la conexión.
"""

from __future__ import annotations

import functools
import hashlib
import json
import threading
from pathlib import Path
from typing import Any

import duckdb

from eim.observability import catalog

SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR);
CREATE TABLE IF NOT EXISTS catalog_versions (
    hash VARCHAR PRIMARY KEY, created_ms BIGINT, n_components INTEGER, n_edges INTEGER);
CREATE TABLE IF NOT EXISTS components (
    catalog_hash VARCHAR, id VARCHAR, layer VARCHAR, stage VARCHAR, kind VARCHAR,
    process VARCHAR, version VARCHAR, cadence VARCHAR, cadence_s INTEGER, built VARCHAR,
    task VARCHAR, title_es VARCHAR, explain_es VARCHAR, PRIMARY KEY (catalog_hash, id));
CREATE TABLE IF NOT EXISTS edges (
    catalog_hash VARCHAR, source VARCHAR, target VARCHAR, artifact VARCHAR,
    PRIMARY KEY (catalog_hash, source, target, artifact));
CREATE TABLE IF NOT EXISTS events (
    event_id VARCHAR PRIMARY KEY, ts_utc BIGINT, process VARCHAR, component_id VARCHAR,
    kind VARCHAR, status VARCHAR, run_id VARCHAR, parent_run_id VARCHAR, trace_id VARCHAR,
    duration_ms DOUBLE, mode VARCHAR, source VARCHAR, coverage DOUBLE, detail VARCHAR,
    indexed_ms BIGINT);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events (ts_utc);
CREATE INDEX IF NOT EXISTS ix_events_trace ON events (trace_id);
CREATE INDEX IF NOT EXISTS ix_events_comp ON events (component_id, ts_utc);
CREATE TABLE IF NOT EXISTS refs (
    event_id VARCHAR, direction VARCHAR, ordinal INTEGER, type VARCHAR, id VARCHAR,
    hash VARCHAR, params_version VARCHAR, PRIMARY KEY (event_id, direction, ordinal));
CREATE INDEX IF NOT EXISTS ix_refs_hash ON refs (hash);
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR PRIMARY KEY, component_id VARCHAR, process VARCHAR, trace_id VARCHAR,
    parent_run_id VARCHAR, started_ms BIGINT, ended_ms BIGINT, status VARCHAR,
    duration_ms DOUBLE, mode VARCHAR, code_version VARCHAR, params_version VARCHAR,
    error VARCHAR);
CREATE INDEX IF NOT EXISTS ix_runs_start ON runs (started_ms);
CREATE TABLE IF NOT EXISTS decisions (
    trace_id VARCHAR PRIMARY KEY, symbol VARCHAR, timeframe VARCHAR, mode VARCHAR,
    first_ms BIGINT, last_ms BIGINT, n_events INTEGER, n_signals INTEGER,
    synthesis_event VARCHAR, forecast_event VARCHAR, plan_event VARCHAR, risk_event VARCHAR,
    risk_status VARCHAR, order_event VARCHAR, sent_event VARCHAR, fill_event VARCHAR,
    outcome VARCHAR, has_error BOOLEAN, links VARCHAR);
CREATE INDEX IF NOT EXISTS ix_decisions_last ON decisions (last_ms);
CREATE TABLE IF NOT EXISTS spool_files (
    file VARCHAR PRIMARY KEY, byte_offset BIGINT, size BIGINT, lines BIGINT, corrupt BIGINT,
    updated_ms BIGINT);
CREATE TABLE IF NOT EXISTS bridge_state (source VARCHAR PRIMARY KEY, watermark BIGINT);
"""

EVENT_COLS = ("event_id", "ts_utc", "process", "component_id", "kind", "status", "run_id",
              "parent_run_id", "trace_id", "duration_ms", "mode", "source", "coverage", "detail",
              "indexed_ms")
RUN_COLS = ("run_id", "component_id", "process", "trace_id", "parent_run_id", "started_ms",
            "ended_ms", "status", "duration_ms", "mode", "code_version", "params_version",
            "error")
DECISION_COLS = ("trace_id", "symbol", "timeframe", "mode", "first_ms", "last_ms", "n_events",
                 "n_signals", "synthesis_event", "forecast_event", "plan_event", "risk_event",
                 "risk_status", "order_event", "sent_event", "fill_event", "outcome",
                 "has_error", "links")
_CHUNK = 2000
_BULK = 20_000


@functools.cache
def catalog_hash() -> str:
    blob = json.dumps([x.model_dump(mode="json") for x in catalog.COMPONENTS], sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _marks(n: int) -> str:
    return ",".join("?" * n)


class ObsStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(self.path)
        self.lock = threading.RLock()
        self._schema: dict[str, dict[str, str]] = {}
        with self.lock:
            self.con.execute(_DDL)
            self.con.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
                             [str(SCHEMA_VERSION)])

    # --- escritura (solo el indexador) ---------------------------------------------------
    def begin(self) -> None:
        self.con.execute("BEGIN TRANSACTION")

    def commit(self) -> None:
        self.con.execute("COMMIT")

    def rollback(self) -> None:
        try:
            self.con.execute("ROLLBACK")
        except duckdb.Error:
            pass

    def existing(self, table: str, key: str, ids: list[str]) -> set[str]:
        out: set[str] = set()
        for i in range(0, len(ids), _CHUNK):
            part = ids[i:i + _CHUNK]
            out.update(r[0] for r in self.con.execute(
                f"SELECT {key} FROM {table} WHERE {key} IN ({_marks(len(part))})",
                part).fetchall())
        return out

    def rows(self, table: str, cols: tuple[str, ...], key: str, ids: list[str]) -> dict:
        out: dict[str, dict[str, Any]] = {}
        for i in range(0, len(ids), _CHUNK):
            part = ids[i:i + _CHUNK]
            for r in self.con.execute(
                    f"SELECT {','.join(cols)} FROM {table} WHERE {key} IN ({_marks(len(part))})",
                    part).fetchall():
                row = dict(zip(cols, r, strict=True))
                out[row[key]] = row
        return out

    def _types(self, table: str) -> dict[str, str]:
        if table not in self._schema:
            self._schema[table] = {r[0]: r[1] for r in self.con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ?", [table]).fetchall()}
        return self._schema[table]

    def insert(self, table: str, cols: tuple[str, ...], rows: list[tuple],
               *, replace: bool = False) -> None:
        """Inserción por columnas (`unnest`): ~70 000 filas/s frente a ~2 000 de `executemany`."""
        if not rows:
            return
        types = self._types(table)
        verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
        sel = ",".join(f"unnest(?::{types[c]}[])" for c in cols)
        for i in range(0, len(rows), _BULK):
            part = rows[i:i + _BULK]
            self.con.execute(f"{verb} INTO {table} ({','.join(cols)}) SELECT * FROM (SELECT {sel})",
                             [list(c) for c in zip(*part, strict=True)])

    def sync_catalog(self, now_ms: int) -> str:
        """Copia versionada del catálogo: una versión nueva solo si cambió su contenido."""
        h = catalog_hash()
        with self.lock:
            if self.con.execute("SELECT 1 FROM catalog_versions WHERE hash = ?", [h]).fetchone():
                return h
            edges = catalog.edges()
            self.begin()
            try:
                self.insert("catalog_versions", ("hash", "created_ms", "n_components", "n_edges"),
                            [(h, now_ms, len(catalog.COMPONENTS), len(edges))])
                self.insert("components", ("catalog_hash", "id", "layer", "stage", "kind",
                                           "process", "version", "cadence", "cadence_s", "built",
                                           "task", "title_es", "explain_es"),
                            [(h, x.id, x.layer, x.stage, x.kind, x.process, x.version, x.cadence,
                              x.cadence_s, x.built, x.task, x.title_es, x.explain_es)
                             for x in catalog.COMPONENTS])
                self.insert("edges", ("catalog_hash", "source", "target", "artifact"),
                            [(h, s, t, a) for s, t, a in edges])
                self.commit()
            except BaseException:
                self.rollback()
                raise
        return h

    # --- lectura -------------------------------------------------------------------------
    def query(self, sql: str, params: list | tuple = ()) -> list[dict[str, Any]]:
        with self.lock:
            cur = self.con.execute(sql, list(params))
            names = [d[0] for d in cur.description]
            return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]

    def scalar(self, sql: str, params: list | tuple = ()) -> Any:
        with self.lock:
            r = self.con.execute(sql, list(params)).fetchone()
        return r[0] if r else None

    def counts(self) -> dict[str, int]:
        with self.lock:
            return {t: self.con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                    for t in ("events", "refs", "runs", "decisions")}

    def close(self) -> None:
        with self.lock:
            self.con.close()
