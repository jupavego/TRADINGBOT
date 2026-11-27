"""T93 — cola: prioridad, caché (invalidación por datos y versión), reintentos, tasa,
reanudación tras caída, cancelación limpia y procesos acotados. Corre sobre la cola en memoria y
sobre la de DuckDB (`scanner.duckdb`), que cumplen el mismo contrato."""

from __future__ import annotations

import importlib.util

import pytest

from eim.scanner.backends import MemoryBackend, make_job
from eim.scanner.jobs import Handler
from eim.scanner.queue import JobQueue, RateLimiter, bounded_procs
from tests.scanner import _helpers as h

HAS_DUCKDB = importlib.util.find_spec("duckdb") is not None


def _memory():
    return MemoryBackend()


def _duck():
    from eim.data.scanner_store import ScannerStore
    return ScannerStore(":memory:")


BACKENDS = [pytest.param(_memory, id="memoria"),
            pytest.param(_duck, id="duckdb",
                         marks=pytest.mark.skipif(not HAS_DUCKDB, reason="sin duckdb"))]


class Clock:
    def __init__(self) -> None:
        self.t = 1_000.0
        self.slept: list[float] = []

    def ms(self) -> int:
        return int(self.t * 1000)

    def mono(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


def handlers(version: str = "1", **extra) -> dict[str, Handler]:
    return {"echo": Handler("echo", h.echo, f"echo:{version}"),
            "boom": Handler("boom", h.boom, "boom:1"),
            "net": Handler("net", h.echo, "net:1", inline=True, cacheable=False,
                           provider="binance"), **extra}


def queue(backend, clock: Clock, **kw) -> JobQueue:
    return JobQueue(backend, backend, handlers=kw.pop("handlers", handlers()), procs=1,
                    clock=clock.ms, sleep=clock.sleep, monotonic=clock.mono, **kw)


def job(kind="echo", inst="crypto.x.AUSDT", data_hash="h1", priority=0, run="r1", x=1, t=0):
    return make_job(run, kind, inst, "1d", "profundo", priority=priority, data_hash=data_hash,
                    payload={"x": x}, t=t)


@pytest.mark.parametrize("make", BACKENDS)
def test_priority_order_and_no_duplicates(make):
    b, c = make(), Clock()
    q = queue(b, c)
    assert q.submit([job(inst="a", priority=1), job(inst="b", priority=5),
                     job(inst="c", priority=3)]) == 3
    assert q.submit([job(inst="a", priority=1)]) == 0            # mismo id: no se duplica
    assert [j.instrument_id for j in b.ready(c.ms(), 10)] == ["b", "c", "a"]
    st = q.run_pending()
    assert st.done == 3 and b.counts()["done"] == 3
    assert b.get(job(inst="b").job_id).result == {"echo": 1, "pid_ok": True}


@pytest.mark.parametrize("make", BACKENDS)
def test_cache_hits_and_is_invalidated_by_new_data_or_new_version(make):
    b, c = make(), Clock()
    q = queue(b, c)
    q.submit([job(run="r1")])
    assert q.run_pending().cached == 0
    q.submit([job(run="r2")])                                    # mismos datos y versión
    st = q.run_pending()
    assert st.cached == 1 and b.get(job(run="r2").job_id).cached
    q.submit([job(run="r3", data_hash="h2")])                    # llegó una vela nueva
    assert q.run_pending().cached == 0
    q2 = queue(b, c, handlers=handlers(version="2"))             # código nuevo del manejador
    q2.submit([job(run="r4", data_hash="h2")])
    assert q2.run_pending().cached == 0
    q2.submit([job(run="r5", data_hash="h2")])
    assert q2.run_pending().cached == 1


@pytest.mark.parametrize("make", BACKENDS)
def test_retries_with_growing_wait_then_fails_with_the_reason(make):
    b, c = make(), Clock()
    q = queue(b, c, max_attempts=3, backoff_s=2.0, max_backoff_s=60.0)
    q.submit([job(kind="boom")])
    st = q.run_pending()
    assert st.retried == 2 and st.failed == 1
    assert c.slept == [2.0, 4.0]                                 # 2 · 2^(intento-1)
    j = b.get(job(kind="boom").job_id)
    assert j.state == "failed" and j.attempts == 3 and "falla a propósito" in j.error


@pytest.mark.parametrize("make", BACKENDS)
def test_unknown_handler_fails_at_once(make):
    b, c = make(), Clock()
    q = queue(b, c)
    q.submit([job(kind="nada")])
    st = q.run_pending()
    assert st.failed == 1 and "desconocido" in b.get(job(kind="nada").job_id).error


@pytest.mark.parametrize("make", BACKENDS)
def test_resume_after_a_crash_puts_running_jobs_back(make):
    b, c = make(), Clock()
    q = queue(b, c, max_attempts=3)
    q.submit([job(inst="a"), job(inst="b")])
    crashed = b.ready(c.ms(), 1)[0].with_(state="running", attempts=1)
    b.update(crashed)                                  # el proceso murió a mitad de este
    exhausted = b.get(job(inst="b").job_id).with_(state="running", attempts=3)
    b.update(exhausted)
    q2 = queue(b, c, max_attempts=3)                   # nueva arrancada, misma base
    assert q2.resume() == 1
    assert b.get(exhausted.job_id).state == "failed"
    st = q2.run_pending()
    assert st.done == 1 and b.get(crashed.job_id).attempts == 2


@pytest.mark.parametrize("make", BACKENDS)
def test_clean_cancel_finishes_nothing_half_and_cancels_the_rest(make):
    b, c = make(), Clock()
    calls = []

    def stop_after_first(payload):
        calls.append(payload["x"])
        q.request_cancel()
        return {"ok": True}
    q = queue(b, c, handlers={"echo": Handler("echo", stop_after_first, "e:1")})
    q.submit([job(inst=f"i{k}", x=k, priority=10 - k) for k in range(5)])
    st = q.run_pending(run_id="r1")
    assert calls == [0] and st.done == 1 and st.cancelled == 4
    assert b.counts() == {"pending": 0, "running": 0, "done": 1, "failed": 0, "cancelled": 4}


@pytest.mark.parametrize("make", BACKENDS)
def test_rate_limit_spaces_network_calls_per_provider(make):
    b, c = make(), Clock()
    q = queue(b, c, rate_limits={"binance": 0.5})                # una cada 2 s
    q.submit([make_job("r", "net", f"i{k}", "1d", "rapido", payload={"x": k}, provider="binance")
              for k in range(3)])
    st = q.run_pending()
    assert st.done == 3 and st.waited_s == pytest.approx(4.0)


def test_rate_limiter_refills_with_time():
    c = Clock()
    rl = RateLimiter(1.0, burst=2, clock=c.mono, sleep=c.sleep)
    assert rl.acquire() == 0 and rl.acquire() == 0 and rl.acquire() == pytest.approx(1.0)
    c.t += 5
    assert rl.acquire() == 0


def test_deadline_stops_the_queue_and_leaves_work_pending():
    b, c = MemoryBackend(), Clock()

    def slow(payload):
        c.t += 10
        return {}
    q = queue(b, c, handlers={"echo": Handler("echo", slow, "s:1")})
    q.submit([job(inst=f"i{k}") for k in range(5)])
    st = q.run_pending(deadline_s=15)
    assert st.deadline_hit and st.done == 2 and b.counts()["pending"] == 3


def test_procs_are_bounded_to_the_machine():
    assert bounded_procs(8, cpu=16) == 2          # nunca más de 2 (T87, CLAUDE.md)
    assert bounded_procs(2, cpu=2) == 1           # deja un núcleo libre
    assert bounded_procs(0, cpu=8) == 1


def test_real_process_pool_runs_jobs_in_other_processes():
    import os

    b = MemoryBackend()
    q = JobQueue(b, b, handlers={"sq": Handler("sq", h.square, "sq:1")}, procs=2)
    if q.procs < 2:
        pytest.skip("este equipo solo admite 1 proceso de trabajo")
    q.submit([make_job("r", "sq", f"i{k}", "1d", "profundo", data_hash=f"d{k}",
                       payload={"x": k}) for k in range(4)])
    try:
        st = q.run_pending()
    finally:
        q.close()
    assert st.done == 4
    res = [b.get(f"r:sq:i{k}:1d").result for k in range(4)]
    assert [r["y"] for r in res] == [0, 1, 4, 9]
    assert all(r["pid"] != os.getpid() for r in res)
