"""Registro del escáner global en DuckDB (T93): `data/scanner/scanner.duckdb`.

Base aparte por la regla de siempre (un proceso escritor por archivo DuckDB): la abre solo el
servicio del escáner. `status` no la abre: lee `status.json` y el latido.

Tablas (`asof` es palabra reservada de DuckDB —`ASOF JOIN`—: la columna se llama `asof_ms`):

- `runs`: una fila por barrido o pasada rápida (ritmo, `asof`, cuántos entraron en cada etapa,
  versión de la fórmula, parámetros, tiempos y costo por instrumento frente al presupuesto).
- `exclusions`: quién salió del embudo, en qué etapa y por qué (motivo y detalle).
- `scores`: la puntuación de cada instrumento por corrida, con su rango, calidad, huella de
  datos y métricas.
- `alerts`: lo que vio el ritmo rápido (precio o diferencial).
- `deep_results` (T94): por instrumento de la lista corta, qué agentes corrieron y cuáles no (y
  por qué), la síntesis, la proyección y la oportunidad o el motivo de que no la haya.
- `opportunities` (T94): las oportunidades candidatas (`eim/core/opportunity.py`), con su hash de
  datos y su `opportunity_id` determinista. Nunca órdenes.
- `attempts` y `attempt_obs` (T95): el registro de intentos del escáner y sus observaciones hacia
  adelante (`eim/data/scanner_attempts.py`).
- `jobs` y `cache`: la cola persistente (reanudable) y la caché por
  `(instrumento, marco, hash de datos, versión)`. Cumple `JobBackend` y `CacheBackend` de
  `eim/scanner/backends.py`.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import duckdb

from eim.data.duck import tune
from eim.data.scanner_attempts import ATTEMPTS_DDL, AttemptRecords
from eim.scanner.backends import STATES, CacheKey, Job

DB_DIR, DB_NAME = "scanner", "scanner.duckdb"
_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR PRIMARY KEY, rhythm VARCHAR, started_at BIGINT, finished_at BIGINT,
    asof_ms BIGINT, timeframe VARCHAR, n_catalog INTEGER, n_stage1 INTEGER, n_stage2 INTEGER,
    n_scored INTEGER, n_shortlist INTEGER, screen_version VARCHAR, params_json VARCHAR,
    timings_json VARCHAR, ms_per_instrument DOUBLE, budget_ms DOUBLE, within_budget BOOLEAN,
    fingerprint VARCHAR, status VARCHAR, detail_json VARCHAR);
CREATE TABLE IF NOT EXISTS exclusions (
    run_id VARCHAR, instrument_id VARCHAR, stage INTEGER, reason VARCHAR, detail VARCHAR,
    PRIMARY KEY (run_id, instrument_id));
CREATE TABLE IF NOT EXISTS scores (
    run_id VARCHAR, instrument_id VARCHAR, rank INTEGER, score DOUBLE, quality DOUBLE,
    data_hash VARCHAR, last_t BIGINT, last_close DOUBLE, metrics_json VARCHAR,
    PRIMARY KEY (run_id, instrument_id));
CREATE TABLE IF NOT EXISTS alerts (
    run_id VARCHAR, t BIGINT, instrument_id VARCHAR, kind VARCHAR, value DOUBLE,
    detail VARCHAR);
CREATE TABLE IF NOT EXISTS deep_results (
    deep_run_id VARCHAR, instrument_id VARCHAR, base_run_id VARCHAR, input_hash VARCHAR,
    opportunity_id VARCHAR, reason VARCHAR, result_json VARCHAR,
    PRIMARY KEY (deep_run_id, instrument_id));
CREATE TABLE IF NOT EXISTS opportunities (
    opportunity_id VARCHAR, deep_run_id VARCHAR, base_run_id VARCHAR, instrument_id VARCHAR,
    side VARCHAR, asof_ms BIGINT, timeframe VARCHAR, input_hash VARCHAR, status VARCHAR,
    opportunity_json VARCHAR, PRIMARY KEY (opportunity_id, deep_run_id));
CREATE TABLE IF NOT EXISTS jobs (
    job_id VARCHAR PRIMARY KEY, run_id VARCHAR, kind VARCHAR, instrument_id VARCHAR,
    timeframe VARCHAR, rhythm VARCHAR, priority INTEGER, data_hash VARCHAR,
    payload_json VARCHAR, provider VARCHAR, state VARCHAR, attempts INTEGER, next_at BIGINT,
    error VARCHAR, result_json VARCHAR, cached BOOLEAN, created_at BIGINT, updated_at BIGINT);
CREATE TABLE IF NOT EXISTS cache (
    instrument_id VARCHAR, timeframe VARCHAR, data_hash VARCHAR, version VARCHAR,
    kind VARCHAR, result_json VARCHAR, created_at BIGINT,
    PRIMARY KEY (instrument_id, timeframe, data_hash, version));
"""
_JOB_COLS = ("job_id", "run_id", "kind", "instrument_id", "timeframe", "rhythm", "priority",
             "data_hash", "payload_json", "provider", "state", "attempts", "next_at", "error",
             "result_json", "cached", "created_at", "updated_at")
_SEL = f"SELECT {', '.join(_JOB_COLS)} FROM jobs"


def _job_row(j: Job) -> list:
    return [j.job_id, j.run_id, j.kind, j.instrument_id, j.timeframe, j.rhythm, j.priority,
            j.data_hash, json.dumps(j.payload, ensure_ascii=False), j.provider, j.state,
            j.attempts, j.next_at, j.error,
            None if j.result is None else json.dumps(j.result, ensure_ascii=False),
            j.cached, j.created_at, j.updated_at]


def _job(r) -> Job:
    d = dict(zip(_JOB_COLS, r, strict=True))
    return Job(job_id=d["job_id"], run_id=d["run_id"], kind=d["kind"],
               instrument_id=d["instrument_id"], timeframe=d["timeframe"], rhythm=d["rhythm"],
               priority=int(d["priority"] or 0), data_hash=d["data_hash"] or "",
               payload=json.loads(d["payload_json"] or "{}"), provider=d["provider"],
               state=d["state"], attempts=int(d["attempts"] or 0), next_at=int(d["next_at"] or 0),
               error=d["error"] or "",
               result=None if d["result_json"] is None else json.loads(d["result_json"]),
               cached=bool(d["cached"]), created_at=int(d["created_at"] or 0),
               updated_at=int(d["updated_at"] or 0))


class DeepRecords:
    """Lo de T94 sobre la misma conexión (mezclado en `ScannerStore`)."""

    def record_deep(self, deep_run_id: str, base_run_id: str, results: list[dict]) -> None:
        rows = [(deep_run_id, r["instrument_id"], base_run_id, r.get("input_hash", ""),
                 (r.get("opportunity") or {}).get("opportunity_id"), r.get("reason", ""),
                 json.dumps(r, ensure_ascii=False)) for r in results]
        opps = [(o["opportunity_id"], deep_run_id, base_run_id, o["instrument_id"], o["side"],
                 o["asof"], o["timeframe"], o["input_hash"], o["status"],
                 json.dumps(o, ensure_ascii=False))
                for o in (r.get("opportunity") for r in results) if o]
        with self._lock:
            if rows:
                self._con.executemany(
                    "INSERT OR REPLACE INTO deep_results VALUES (?,?,?,?,?,?,?)", rows)
            if opps:
                self._con.executemany(
                    "INSERT OR REPLACE INTO opportunities VALUES (?,?,?,?,?,?,?,?,?,?)", opps)

    def deep_results_of(self, deep_run_id: str) -> list[dict]:
        rows = self._q("SELECT result_json FROM deep_results WHERE deep_run_id = ? "
                       "ORDER BY instrument_id", [deep_run_id])
        return [json.loads(r[0]) for r in rows]

    def opportunities_of(self, deep_run_id: str) -> list[dict]:
        rows = self._q("SELECT opportunity_json FROM opportunities WHERE deep_run_id = ? "
                       "ORDER BY instrument_id", [deep_run_id])
        return [json.loads(r[0]) for r in rows]

    def opportunity(self, opportunity_id: str) -> dict | None:
        rows = self._q("SELECT opportunity_json FROM opportunities WHERE opportunity_id = ? "
                       "ORDER BY asof_ms DESC LIMIT 1", [opportunity_id])
        return json.loads(rows[0][0]) if rows else None

    def run_info(self, run_id: str) -> dict | None:
        rows = self._q("SELECT run_id, rhythm, asof_ms, timeframe, detail_json, started_at, "
                       "finished_at FROM runs WHERE run_id = ?", [run_id])
        return _run_row(rows[0]) if rows else None

    def recent_runs(self, limit: int = 20) -> list[dict]:
        rows = self._q("SELECT run_id, rhythm, asof_ms, timeframe, detail_json, started_at, "
                       f"finished_at FROM runs ORDER BY finished_at DESC LIMIT {int(limit)}")
        return [_run_row(r) for r in rows]


def _run_row(r) -> dict:
    return {"run_id": r[0], "rhythm": r[1], "asof": r[2], "timeframe": r[3],
            "detail": json.loads(r[4] or "{}"), "started_at": r[5], "finished_at": r[6]}


class ScannerStore(DeepRecords, AttemptRecords):
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(self.path)
        tune(self._con)
        self._con.execute(_DDL)
        self._con.execute(ATTEMPTS_DDL)
        self._lock = threading.Lock()

    def close(self) -> None:
        self._con.close()

    def _q(self, sql: str, params: list | None = None) -> list:
        with self._lock:
            return self._con.execute(sql, params or []).fetchall()

    def _x(self, sql: str, params: list | None = None) -> None:
        with self._lock:
            self._con.execute(sql, params or [])

    # --- JobBackend -----------------------------------------------------------------------------
    def put(self, jobs: list[Job]) -> int:
        if not jobs:
            return 0
        ph = ",".join("?" * len(_JOB_COLS))
        with self._lock:
            before = self._con.execute("SELECT count(*) FROM jobs").fetchone()[0]
            self._con.executemany(f"INSERT OR IGNORE INTO jobs VALUES ({ph})",
                                  [_job_row(j) for j in jobs])
            after = self._con.execute("SELECT count(*) FROM jobs").fetchone()[0]
        return int(after - before)

    def update(self, job: Job) -> None:
        self._x(f"INSERT OR REPLACE INTO jobs VALUES ({','.join('?' * len(_JOB_COLS))})",
                _job_row(job))

    def get(self, job_id: str) -> Job | None:
        rows = self._q(f"{_SEL} WHERE job_id = ?", [job_id])
        return _job(rows[0]) if rows else None

    def ready(self, now: int, limit: int) -> list[Job]:
        rows = self._q(f"{_SEL} WHERE state = 'pending' AND next_at <= ? "
                       f"ORDER BY priority DESC, created_at, job_id LIMIT {int(limit)}", [now])
        return [_job(r) for r in rows]

    def by_state(self, state: str, run_id: str | None = None) -> list[Job]:
        q, p = f"{_SEL} WHERE state = ?", [state]
        if run_id is not None:
            q, p = q + " AND run_id = ?", [*p, run_id]
        return [_job(r) for r in self._q(q + " ORDER BY priority DESC, created_at, job_id", p)]

    def next_retry_at(self) -> int | None:
        r = self._q("SELECT min(next_at) FROM jobs WHERE state = 'pending'")
        return int(r[0][0]) if r and r[0][0] is not None else None

    def counts(self, run_id: str | None = None) -> dict[str, int]:
        q, p = "SELECT state, count(*) FROM jobs", []
        if run_id is not None:
            q, p = q + " WHERE run_id = ?", [run_id]
        out = dict.fromkeys(STATES, 0)
        out.update({str(s): int(n) for s, n in self._q(q + " GROUP BY state", p)})
        return out

    # --- CacheBackend ---------------------------------------------------------------------------
    def cache_get(self, key: CacheKey) -> dict | None:
        r = self._q("SELECT result_json FROM cache WHERE instrument_id = ? AND timeframe = ? "
                    "AND data_hash = ? AND version = ?", list(key))
        return json.loads(r[0][0]) if r else None

    def cache_put(self, key: CacheKey, kind: str, result: dict, t: int) -> None:
        self._x("INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?,?,?)",
                [*key, kind, json.dumps(result, ensure_ascii=False), int(t)])

    def cache_size(self) -> int:
        return int(self._q("SELECT count(*) FROM cache")[0][0])

    # --- corridas -------------------------------------------------------------------------------
    def record_run(self, run: dict) -> None:
        cols = ("run_id", "rhythm", "started_at", "finished_at", "asof_ms", "timeframe",
                "n_catalog", "n_stage1", "n_stage2", "n_scored", "n_shortlist",
                "screen_version", "params_json", "timings_json", "ms_per_instrument",
                "budget_ms", "within_budget", "fingerprint", "status", "detail_json")
        vals = [run.get("asof" if c == "asof_ms" else c) for c in cols]
        for k in ("params_json", "timings_json", "detail_json"):
            i = cols.index(k)
            if not isinstance(vals[i], str) and vals[i] is not None:
                vals[i] = json.dumps(vals[i], ensure_ascii=False)
        self._x(f"INSERT OR REPLACE INTO runs ({', '.join(cols)}) VALUES "
                f"({','.join('?' * len(cols))})", vals)

    def record_exclusions(self, run_id: str, rows: list[tuple[str, int, str, str]]) -> None:
        if rows:
            with self._lock:
                self._con.executemany("INSERT OR REPLACE INTO exclusions VALUES (?,?,?,?,?)",
                                      [(run_id, *r) for r in rows])

    def record_scores(self, run_id: str, rows: list[dict]) -> None:
        data = [(run_id, r["instrument_id"], r["rank"], r["score"], r["quality"],
                 r.get("data_hash", ""), r.get("last_t"), r.get("last_close"),
                 json.dumps(r.get("metrics", {}), ensure_ascii=False)) for r in rows]
        if data:
            with self._lock:
                self._con.executemany("INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?,?,?,?)",
                                      data)

    def record_alerts(self, run_id: str, rows: list[dict]) -> None:
        data = [(run_id, a["t"], a["instrument_id"], a["kind"], a["value"], a.get("detail", ""))
                for a in rows]
        if data:
            with self._lock:
                self._con.executemany("INSERT INTO alerts VALUES (?,?,?,?,?,?)", data)

    def last_run(self, rhythm: str = "profundo") -> dict | None:
        rows = self._q("SELECT run_id, asof_ms, timeframe FROM runs WHERE rhythm = ? AND "
                       "status = 'ok' ORDER BY finished_at DESC LIMIT 1", [rhythm])
        return {"run_id": rows[0][0], "asof": int(rows[0][1]), "timeframe": rows[0][2]} \
            if rows else None

    def scores_of(self, run_id: str) -> list[dict]:
        rows = self._q("SELECT instrument_id, rank, score, quality, data_hash, last_t, last_close,"
                       " metrics_json FROM scores WHERE run_id = ? ORDER BY rank", [run_id])
        return [{"instrument_id": r[0], "rank": int(r[1]), "score": r[2], "quality": r[3],
                 "data_hash": r[4], "last_t": r[5], "last_close": r[6],
                 "metrics": json.loads(r[7] or "{}")} for r in rows]

    def exclusion_counts(self, run_id: str) -> dict[str, int]:
        return {str(k): int(n) for k, n in self._q(
            "SELECT reason, count(*) FROM exclusions WHERE run_id = ? GROUP BY reason "
            "ORDER BY reason", [run_id])}

    def exclusions_by_class(self, run_id: str) -> dict[str, dict[str, int]]:
        """T102: {clase: {motivo: n}} del barrido (la clase es el prefijo del id del registro)."""
        out: dict[str, dict[str, int]] = {}
        for cls, reason, n in self._q(
                "SELECT split_part(instrument_id, '.', 1), reason, count(*) FROM exclusions "
                "WHERE run_id = ? GROUP BY 1, 2 ORDER BY 1, 2", [run_id]):
            out.setdefault(str(cls), {})[str(reason)] = int(n)
        return out


def open_scanner_store(data_dir: str | Path) -> ScannerStore:
    return ScannerStore(Path(data_dir) / DB_DIR / DB_NAME)
