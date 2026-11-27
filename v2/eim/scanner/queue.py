"""Cola del escáner (T93): prioridad, procesos acotados, caché, reintentos, tasa y reanudación.

- **Prioridad**: sale antes el trabajo de mayor `priority`; a igualdad, el más antiguo.
- **Procesos acotados al equipo** (`bounded_procs`): como mucho `max_procs` (2 en estos equipos,
  T87) y nunca todos los núcleos. T87 midió que los hilos no aceleran a los agentes (el GIL los
  serializa): el paralelismo es por **procesos sobre instrumentos**. Con 1 proceso, en línea.
- **Caché** por `(instrumento, marco, hash de datos, versión del manejador)`: los mismos datos con
  el mismo código no se recalculan; una vela nueva o una versión nueva invalidan sola la entrada.
- **Reintentos con espera** creciente (`backoff_s · 2^(intento-1)`, tope `max_backoff_s`).
- **Límite de tasa por proveedor** (`RateLimiter`, cubo de fichas): los trabajos de red esperan
  su turno en vez de gastar el peso que comparte la corrida de T31.
- **Reanudación**: `resume()` devuelve a la cola lo que quedó `running` tras una caída.
- **Cancelación limpia**: `request_cancel()` deja terminar lo que está en curso, no empieza nada
  más y marca lo pendiente como `cancelled` (nada queda a medias).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import asdict, dataclass

from eim.scanner.backends import CacheBackend, Job, JobBackend
from eim.scanner.jobs import HANDLERS, Handler

HARD_MAX_PROCS = 2


def bounded_procs(requested: int, cpu: int | None = None) -> int:
    """Procesos de trabajo permitidos: ≤ lo pedido, ≤ 2, ≤ núcleos − 1, y al menos 1."""
    cpu = cpu if cpu is not None else (os.cpu_count() or 2)
    return max(1, min(int(requested), HARD_MAX_PROCS, cpu - 1))


class RateLimiter:
    """Cubo de fichas: `rate` llamadas por segundo con ráfaga `burst`."""

    def __init__(self, rate: float, burst: int = 1, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], object] = time.sleep) -> None:
        if rate <= 0:
            raise ValueError("rate > 0")
        self.rate, self.burst, self._clock, self._sleep = rate, max(1, burst), clock, sleep
        self._tokens, self._t = float(self.burst), clock()

    def acquire(self) -> float:
        """Toma una ficha; si no hay, espera. Devuelve los segundos esperados."""
        now = self._clock()
        self._tokens = min(self.burst, self._tokens + (now - self._t) * self.rate)
        self._t = now
        waited = 0.0
        if self._tokens < 1:
            waited = (1 - self._tokens) / self.rate
            self._sleep(waited)
            self._t = self._clock()
            self._tokens = 1.0
        self._tokens -= 1
        return waited


@dataclass
class QueueStats:
    done: int = 0
    cached: int = 0
    failed: int = 0
    retried: int = 0
    cancelled: int = 0
    resumed: int = 0
    waited_s: float = 0.0
    deadline_hit: bool = False

    @property
    def processed(self) -> int:
        return self.done + self.failed + self.retried

    @property
    def cache_hit_rate(self) -> float | None:
        n = self.done
        return self.cached / n if n else None

    def as_json(self) -> dict:
        return asdict(self) | {"cache_hit_rate": self.cache_hit_rate}


class JobQueue:
    def __init__(self, backend: JobBackend, cache: CacheBackend, *,
                 handlers: Mapping[str, Handler] = HANDLERS, procs: int = 1,
                 max_attempts: int = 3, backoff_s: float = 2.0, max_backoff_s: float = 60.0,
                 rate_limits: Mapping[str, float] | None = None,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000),
                 sleep: Callable[[float], object] = time.sleep,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.backend, self.cache, self.handlers = backend, cache, handlers
        self.procs = bounded_procs(procs)
        self.max_attempts, self.backoff_s = max_attempts, backoff_s
        self.max_backoff_s = max_backoff_s
        self.clock, self.sleep, self.monotonic = clock, sleep, monotonic
        self.limits = {k: RateLimiter(v, clock=monotonic, sleep=sleep)
                       for k, v in (rate_limits or {}).items()}
        self._cancel = False
        self._pool: ProcessPoolExecutor | None = None

    # --- ciclo de vida ------------------------------------------------------------------------
    def submit(self, jobs: list[Job]) -> int:
        return self.backend.put(jobs)

    def resume(self) -> int:
        """Lo que quedó `running` (el proceso se cayó a mitad) vuelve a la cola o, si ya agotó
        sus intentos, queda `failed` con el motivo."""
        now, n = self.clock(), 0
        for j in self.backend.by_state("running"):
            if j.attempts >= self.max_attempts:
                self.backend.update(j.with_(state="failed", updated_at=now,
                                            error=f"interrumpido {j.attempts} veces"))
            else:
                self.backend.update(j.with_(state="pending", next_at=now, updated_at=now))
                n += 1
        return n

    def request_cancel(self) -> None:
        self._cancel = True

    def cancel_pending(self, run_id: str | None = None) -> int:
        now, n = self.clock(), 0
        for j in self.backend.by_state("pending", run_id):
            self.backend.update(j.with_(state="cancelled", updated_at=now,
                                        error="cancelado antes de empezar"))
            n += 1
        return n

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None

    # --- ejecución ----------------------------------------------------------------------------
    def run_pending(self, *, max_jobs: int | None = None, deadline_s: float | None = None,
                    run_id: str | None = None) -> QueueStats:
        st = QueueStats()
        end = self.monotonic() + deadline_s if deadline_s is not None else None
        while not self._cancel and (max_jobs is None or st.processed < max_jobs):
            if end is not None and self.monotonic() >= end:
                st.deadline_hit = True
                break
            now = self.clock()
            limit = max(1, self.procs * 2)
            if max_jobs is not None:
                limit = min(limit, max_jobs - st.processed)
            batch = self.backend.ready(now, limit)
            if not batch:
                nxt = self.backend.next_retry_at()
                if nxt is None:
                    break
                wait = max(0.0, (nxt - now) / 1000)
                if end is not None and self.monotonic() + wait > end:
                    st.deadline_hit = True
                    break
                self.sleep(wait)
                continue
            self._run_batch(batch, st)
        if self._cancel:
            st.cancelled += self.cancel_pending(run_id)
        return st

    def _run_batch(self, batch: list[Job], st: QueueStats) -> None:
        pooled: list[tuple[Job, Handler]] = []
        for job in batch:
            if self._cancel:              # lo que no empezó se queda pendiente (y se cancela)
                break
            h = self.handlers.get(job.kind)
            if h is None:
                self._finish(job.with_(attempts=job.attempts + 1), st,
                             error=f"manejador desconocido: {job.kind}", final=True)
                continue
            key = (job.instrument_id, job.timeframe, job.data_hash, h.version)
            hit = self.cache.cache_get(key) if h.cacheable and job.data_hash else None
            if hit is not None:
                self._finish(job, st, result=hit, cached=True)
                continue
            job = job.with_(state="running", attempts=job.attempts + 1, updated_at=self.clock())
            self.backend.update(job)
            if h.inline or self.procs < 2:
                if h.provider and h.provider in self.limits:
                    st.waited_s += self.limits[h.provider].acquire()
                try:
                    self._finish(job, st, result=h.fn(job.payload), handler=h)
                except Exception as exc:  # noqa: BLE001 - un trabajo no tumba la cola
                    self._finish(job, st, error=f"{type(exc).__name__}: {exc}"[:300])
            else:
                pooled.append((job, h))
        if pooled:
            self._run_pooled(pooled, st)

    def _run_pooled(self, pooled: list[tuple[Job, Handler]], st: QueueStats) -> None:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=self.procs)
        futs: list[tuple[Job, Handler, Future]] = [
            (j, h, self._pool.submit(h.fn, j.payload)) for j, h in pooled]
        for job, h, fut in futs:
            try:
                self._finish(job, st, result=fut.result(), handler=h)
            except Exception as exc:  # noqa: BLE001 - un trabajo no tumba la cola
                self._finish(job, st, error=f"{type(exc).__name__}: {exc}"[:300])

    def _finish(self, job: Job, st: QueueStats, *, result: dict | None = None,
                error: str | None = None, cached: bool = False, handler: Handler | None = None,
                final: bool = False) -> None:
        now = self.clock()
        if error is None:
            if handler is not None and handler.cacheable and job.data_hash:
                key = (job.instrument_id, job.timeframe, job.data_hash, handler.version)
                self.cache.cache_put(key, job.kind, result or {}, now)
            self.backend.update(job.with_(state="done", result=result or {}, cached=cached,
                                          error="", updated_at=now))
            st.done += 1
            st.cached += int(cached)
            return
        if not final and job.attempts < self.max_attempts:
            wait = min(self.max_backoff_s, self.backoff_s * 2 ** (job.attempts - 1))
            self.backend.update(job.with_(state="pending", error=error, updated_at=now,
                                          next_at=now + int(wait * 1000)))
            st.retried += 1
        else:
            self.backend.update(job.with_(state="failed", error=error, updated_at=now))
            st.failed += 1
