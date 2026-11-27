"""Trabajos de la cola del escáner y dónde se guardan (T93).

Un trabajo es `(instrumento, marco, ritmo)` más el manejador que lo resuelve (`kind`), su
prioridad y la huella de los datos con que se pidió. Se guarda **antes** de ejecutarse y se
marca `running` al empezar: si el proceso se cae, la siguiente arrancada encuentra los
`running` huérfanos y los devuelve a la cola (`JobQueue.resume`).

Aquí viven el contrato de almacenamiento (`JobBackend`, `CacheBackend`) y su versión en
memoria, que usan las pruebas y el informe de presupuesto. La de disco, en DuckDB, está en
`eim/data/scanner_store.py` y cumple el mismo contrato.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from typing import Literal, Protocol

State = Literal["pending", "running", "done", "failed", "cancelled"]
Rhythm = Literal["rapido", "profundo"]
STATES: tuple[str, ...] = ("pending", "running", "done", "failed", "cancelled")
CacheKey = tuple[str, str, str, str]     # (instrumento, marco, hash de datos, versión)


@dataclass
class Job:
    job_id: str
    run_id: str
    kind: str                      # manejador (`eim/scanner/jobs.HANDLERS`)
    instrument_id: str
    timeframe: str
    rhythm: Rhythm
    priority: int = 0              # mayor = antes
    data_hash: str = ""
    payload: dict = field(default_factory=dict)
    provider: str | None = None    # límite de tasa que consume (None = ninguno)
    state: State = "pending"
    attempts: int = 0
    next_at: int = 0               # ms epoch: no antes de este instante (espera entre reintentos)
    error: str = ""
    result: dict | None = None
    cached: bool = False
    created_at: int = 0
    updated_at: int = 0

    def with_(self, **kw) -> Job:
        return replace(self, **kw)


def make_job(run_id: str, kind: str, instrument_id: str, timeframe: str, rhythm: Rhythm, *,
             priority: int = 0, data_hash: str = "", payload: dict | None = None,
             provider: str | None = None, t: int = 0) -> Job:
    """Trabajo con id determinista: pedir dos veces lo mismo en una corrida no lo duplica."""
    return Job(job_id=f"{run_id}:{kind}:{instrument_id}:{timeframe}", run_id=run_id, kind=kind,
               instrument_id=instrument_id, timeframe=timeframe, rhythm=rhythm,
               priority=priority, data_hash=data_hash, payload=dict(payload or {}),
               provider=provider, next_at=t, created_at=t, updated_at=t)


def ready_order(j: Job) -> tuple:
    return (-j.priority, j.created_at, j.job_id)


class JobBackend(Protocol):
    def put(self, jobs: list[Job]) -> int: ...
    def update(self, job: Job) -> None: ...
    def get(self, job_id: str) -> Job | None: ...
    def ready(self, now: int, limit: int) -> list[Job]: ...
    def by_state(self, state: str, run_id: str | None = None) -> list[Job]: ...
    def next_retry_at(self) -> int | None: ...
    def counts(self, run_id: str | None = None) -> dict[str, int]: ...


class CacheBackend(Protocol):
    def cache_get(self, key: CacheKey) -> dict | None: ...
    def cache_put(self, key: CacheKey, kind: str, result: dict, t: int) -> None: ...


class MemoryBackend:
    """Cola y caché en memoria (pruebas, informe de presupuesto). Seguro entre hilos."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._cache: dict[CacheKey, dict] = {}
        self._lock = threading.Lock()

    def put(self, jobs: list[Job]) -> int:
        n = 0
        with self._lock:
            for j in jobs:
                if j.job_id not in self._jobs:
                    self._jobs[j.job_id] = j.with_()
                    n += 1
        return n

    def update(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.job_id] = job.with_()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            j = self._jobs.get(job_id)
        return j.with_() if j else None

    def ready(self, now: int, limit: int) -> list[Job]:
        with self._lock:
            ok = [j for j in self._jobs.values() if j.state == "pending" and j.next_at <= now]
        return [j.with_() for j in sorted(ok, key=ready_order)[:limit]]

    def by_state(self, state: str, run_id: str | None = None) -> list[Job]:
        with self._lock:
            out = [j.with_() for j in self._jobs.values()
                   if j.state == state and (run_id is None or j.run_id == run_id)]
        return sorted(out, key=ready_order)

    def next_retry_at(self) -> int | None:
        with self._lock:
            ts = [j.next_at for j in self._jobs.values() if j.state == "pending"]
        return min(ts) if ts else None

    def counts(self, run_id: str | None = None) -> dict[str, int]:
        out = dict.fromkeys(STATES, 0)
        with self._lock:
            for j in self._jobs.values():
                if run_id is None or j.run_id == run_id:
                    out[j.state] += 1
        return out

    def cache_get(self, key: CacheKey) -> dict | None:
        with self._lock:
            r = self._cache.get(key)
        return dict(r) if r is not None else None

    def cache_put(self, key: CacheKey, kind: str, result: dict, t: int) -> None:
        with self._lock:
            self._cache[key] = dict(result)

    def cache_size(self) -> int:
        with self._lock:
            return len(self._cache)
