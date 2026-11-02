"""Cola de trabajos pesados (T127): admisión por margen, pausa si la captura sufre, reanudación
sola, cancelación, relevo del ejecutor y un trabajo a la vez."""

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from eim.operation import jobs
from eim.operation.jobs_store import (
    CANCELLED,
    DONE,
    INTERRUPTED,
    PAUSED,
    PENDING,
    RUNNING,
    WAITING,
    Store,
)
from eim.operation.watchdog import instance_lock

COUNTER = ("import pathlib, sys, time\np = pathlib.Path(sys.argv[1])\n"
           "for n in range(1, int(sys.argv[2]) + 1):\n    p.write_text(str(n))\n"
           "    time.sleep(0.05)\n")


def beat(data_dir: Path, queue: int = 0, gaps: dict | None = None, run: int = 1) -> None:
    d = data_dir / "micro_hft"
    d.mkdir(parents=True, exist_ok=True)
    (d / "heartbeat.json").write_text(json.dumps({
        "last_heartbeat": int(time.time() * 1000), "started_at": run, "queue": queue,
        "write_backlog": 0, "dropped": 0, "gaps": gaps or {}}))


def calm(tmp_path: Path) -> jobs.Monitor:
    return jobs.Monitor(tmp_path, ram=lambda: 8000, cpu=lambda: 5.0)


def until(cond, timeout: float = 15.0) -> None:
    end = time.time() + timeout
    while not cond():
        assert time.time() < end, "no llegó a tiempo"
        time.sleep(0.02)


def state(store: Store, job_id: str) -> str | None:
    return j.state if (j := store.get(job_id)) is not None else None


def count(p: Path) -> int:
    try:
        return int(p.read_text() or 0)
    except (OSError, ValueError):       # el trabajo lo está escribiendo
        return -1


def events(store: Store) -> list[str]:
    return [json.loads(x)["event"] for f in sorted(store.logs.glob("*.jsonl"))
            for x in f.read_text("utf-8").splitlines()]


def test_capture_pressure_reads_the_heartbeat():
    now = 1_000_000.0
    hb = {"last_heartbeat": now * 1000, "started_at": 5, "queue": 3, "write_backlog": 0,
          "gaps": {"silencio": 2}, "dropped": 0, "pending_dropped": 0}
    why, prev = jobs.capture_pressure(hb, None, now)
    assert why == [] and prev == {"run": 5, "gaps": 2, "dropped": 0}
    worse = {**hb, "queue": 4000, "write_backlog": 500, "gaps": {"silencio": 3, "secuencia": 1},
             "dropped": 7}
    assert jobs.capture_pressure(worse, prev, now)[0] == [
        "cola de la captura en 4000 mensajes", "escritura de la captura atrasada (500)",
        "2 huecos nuevos en la captura", "7 mensajes descartados"]
    assert jobs.capture_pressure({**hb, "started_at": 6}, prev, now)[0] == [
        "la captura se reinició"]
    stale = {**hb, "queue": 9999, "last_heartbeat": (now - 300) * 1000}
    assert jobs.capture_pressure(stale, prev, now) == ([], None)   # parada: nada que proteger
    assert jobs.capture_pressure(None, prev, now) == ([], None)


def test_a_cpu_job_pauses_when_the_capture_suffers_and_resumes_alone(tmp_path):
    beat(tmp_path)
    store, out = Store(tmp_path), tmp_path / "n.txt"
    job = store.new("prueba", [sys.executable, "-c", COUNTER, str(out), "80"], tmp_path)
    said: list[str] = []
    runner = jobs.Runner(store, calm(tmp_path), poll_s=0.05, resume_after_s=0.5,
                         say=said.append)
    t = threading.Thread(target=runner.drain)
    t.start()
    try:
        until(lambda: count(out) >= 5)
        beat(tmp_path, queue=5000)                       # estrés simulado en la captura
        until(lambda: state(store, job.id) == PAUSED)
        a = count(out)
        time.sleep(0.6)
        assert count(out) == a                      # suspendido de verdad
        beat(tmp_path, queue=0)
        until(lambda: state(store, job.id) == RUNNING)
        until(lambda: count(out) > a)              # siguió solo
    finally:
        t.join(30)
    j = store.get(job.id)
    assert (j.state, j.rc, j.pauses, out.read_text()) == (DONE, 0, 1, "80")
    assert j.paused_s >= 0.5
    assert events(store) == ["encolado", "arranca", "pausa", "reanuda", "termina"]
    assert any("cola de la captura en 5000" in s for s in said)


def test_without_margin_the_job_waits_and_can_be_cancelled(tmp_path):
    store = Store(tmp_path)
    job = store.new("pesado", [sys.executable, "-c", "pass"], tmp_path, min_ram_mb=4096)
    mon = jobs.Monitor(tmp_path, ram=lambda: 3000, cpu=lambda: 95.0)
    t = threading.Thread(target=jobs.Runner(store, mon, poll_s=0.05, say=lambda s: None).drain)
    t.start()
    until(lambda: state(store, job.id) == WAITING)
    time.sleep(0.3)
    assert store.cancel(job.id)
    t.join(10)
    assert store.get(job.id).state == CANCELLED and store.get(job.id).started is None
    assert events(store) == ["encolado", "esperando_margen", "termina"]   # sin repetir el motivo


def test_a_running_job_can_be_cancelled(tmp_path):
    store = Store(tmp_path)
    job = store.new("largo", [sys.executable, "-c", "import time; time.sleep(60)"], tmp_path)
    t = threading.Thread(target=jobs.Runner(store, calm(tmp_path), poll_s=0.05,
                                            say=lambda s: None).drain)
    t.start()
    until(lambda: state(store, job.id) == RUNNING)
    t0 = time.time()
    store.cancel(job.id)
    t.join(30)
    assert store.get(job.id).state == CANCELLED and time.time() - t0 < 10


def test_leftovers_of_a_dead_runner_are_marked_interrupted(tmp_path):
    store = Store(tmp_path)
    job = store.new("viejo", ["x"], tmp_path)
    job.state = PAUSED
    store.save(job)
    jobs.Runner(store, calm(tmp_path), say=lambda s: None).drain()
    assert store.get(job.id).state == INTERRUPTED


def test_submit_returns_the_exit_code_and_shows_the_output(tmp_path):
    said: list[str] = []
    code = "import sys; print('salida del trabajo'); sys.exit(7)"
    rc = jobs.submit(tmp_path, "falla", [sys.executable, "-c", code], tmp_path,
                     monitor=calm(tmp_path), poll_s=0.05, say=said.append)
    assert rc == 7 and "salida del trabajo" in said[-1]
    assert [j.state for j in Store(tmp_path).all()] == ["fallido"]


def test_a_second_submitter_waits_its_turn_and_takes_over(tmp_path):
    lock = instance_lock(tmp_path / "jobs" / "runner.lock")     # otro ejecutor en marcha
    res: list[int] = []
    t = threading.Thread(target=lambda: res.append(jobs.submit(
        tmp_path, "segundo", [sys.executable, "-c", "pass"], tmp_path, monitor=calm(tmp_path),
        poll_s=0.05, say=lambda s: None)))
    t.start()
    time.sleep(0.5)
    assert [j.state for j in Store(tmp_path).all()] == [PENDING]   # no corre a la vez
    lock.close()                                                 # aquel termina (o muere)
    t.join(30)
    assert res == [0] and Store(tmp_path).all()[0].state == DONE


@pytest.mark.skipif(sys.platform != "win32", reason="clases de prioridad de Windows")
def test_the_job_and_its_children_run_at_idle(tmp_path):
    from eim.operation import usage_win

    out = tmp_path / "prio.txt"
    code = ("import sys, pathlib, os\nfrom eim.operation import usage_win\n"
            "pathlib.Path(sys.argv[1]).write_text(str(usage_win.snapshot()[os.getpid()].prio))\n")
    assert jobs.submit(tmp_path, "nivel", [sys.executable, "-c", code, str(out)],
                       Path.cwd(), monitor=calm(tmp_path), poll_s=0.05,
                       say=lambda s: None) == 0
    assert out.read_text() == "4" and usage_win.supported()      # 4 = IDLE


class _PressureOnce(jobs.Monitor):
    """Presión simulada en la captura durante unos sondeos, en cuanto el trabajo arranca."""

    def __init__(self, data_dir: Path, flag: Path) -> None:
        super().__init__(data_dir, ram=lambda: 8000, cpu=lambda: 5.0)
        self.flag, self.n = flag, 0

    def pressure(self) -> list[str]:
        if self.flag.exists() and self.n < 3:
            self.n += 1
            return ["presión simulada"]
        return []


def test_a_job_that_fails_after_a_pause_is_repeated_once(tmp_path):
    """T116: un plazo de reloj caduca con el trabajo congelado; se repite, no se da por malo."""
    flag = tmp_path / "arranco"
    code = ("import pathlib, sys, time\nf = pathlib.Path(sys.argv[1])\nfirst = not f.exists()\n"
            "f.write_text('x')\ntime.sleep(0.5)\nsys.exit(1 if first else 0)\n")
    said: list[str] = []
    rc = jobs.submit(tmp_path, "gate", [sys.executable, "-c", code, str(flag)], tmp_path,
                     monitor=_PressureOnce(tmp_path, flag), poll_s=0.05, say=said.append,
                     retry_paused=1, resume_after_s=0.1)
    runs = Store(tmp_path).all()
    assert rc == 0 and [(j.state, j.pauses) for j in runs] == [("fallido", 1), ("hecho", 0)]
    assert any("se repite" in s for s in said)
    # sin pausas, un fallo es un fallo: no se repite
    code_fail = "import sys; sys.exit(5)"
    assert jobs.submit(tmp_path, "otro", [sys.executable, "-c", code_fail], tmp_path,
                       monitor=calm(tmp_path), poll_s=0.05, say=said.append, retry_paused=1) == 5
    assert [j.state for j in Store(tmp_path).all()][-1] == "fallido" and len(
        Store(tmp_path).all()) == 3
