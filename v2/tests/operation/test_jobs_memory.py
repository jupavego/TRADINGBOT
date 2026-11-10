"""T149: un trabajo pausado no puede retener la memoria que lo pausa. Reproduce el 9-nov con un
monitor falso: la RAM libre es lo que deja el trabajo vivo y no vuelve al pausarlo."""

import json
import sys
import threading
import time

from eim.operation import jobs
from eim.operation import jobs_memory as mem
from eim.operation.jobs_proc import JobProcess
from eim.operation.jobs_store import DONE, FAILED, WAITING, Store

SLEEP = [sys.executable, "-c", "import time; time.sleep(60)"]


class World:
    """El equipo: RAM libre sin el trabajo (`base`) menos lo que retiene el trabajo vivo. Pausar
    no cambia nada; matarlo devuelve su memoria y, si se indica, otros liberan más (`bases`)."""

    def __init__(self, base: int, mems: list[float], bases: list[int] | None = None,
                 on_start: int | None = None) -> None:
        self.base, self.mems, self.bases, self.holding = base, list(mems), list(bases or []), 0.0
        self.on_start = on_start                         # otro programa que llega tras arrancar

    def free(self) -> int:
        return int(self.base - self.holding)

    def spawn(self):
        world = self

        class Heavy(JobProcess):
            def __init__(self, *a, **k) -> None:
                super().__init__(*a, **k)
                self.mb = world.mems.pop(0) if len(world.mems) > 1 else world.mems[0]
                world.holding = self.mb
                if world.on_start is not None:
                    world.base = world.on_start

            def memory_mb(self) -> float:
                return self.mb

            def kill(self) -> None:
                world.holding = 0.0
                if world.bases:
                    world.base = world.bases.pop(0)
                super().kill()

        return Heavy


def monitor(tmp_path, world: World) -> jobs.Monitor:
    return jobs.Monitor(tmp_path, ram=world.free, cpu=lambda: 5.0, ram_total=lambda: 16_000)


def until(cond, timeout: float = 20.0) -> None:
    end = time.time() + timeout
    while not cond():
        assert time.time() < end, "no llegó a tiempo"
        time.sleep(0.02)


def log(store: Store) -> list[dict]:
    return [json.loads(x) for f in sorted(store.logs.glob("*.jsonl"))
            for x in f.read_text("utf-8").splitlines()]


def names(store: Store) -> list[str]:
    return [r["event"] for r in log(store)]


def run(store, mon, world, **kw) -> threading.Thread:
    r = jobs.Runner(store, mon, poll_s=0.05, say=lambda s: None, spawn=world.spawn(), **kw)
    t = threading.Thread(target=r.drain, daemon=True)   # si una prueba falla, no cuelga la suite
    t.start()
    return t


def test_the_9_nov_job_is_requeued_instead_of_paused_forever(tmp_path, monkeypatch):
    """`t143-maker`: pidió 2 500 MB, retuvo 6 800 y dejó 300 libres. Antes: 32 pausas en 5 h 39 min.
    Ahora: ninguna pausa; se mata, la RAM vuelve y espera, con tope, a que quepa lo que usa."""
    monkeypatch.setattr(mem, "REQUEUE_WAIT_S", 1.0)
    world = World(base=7100, mems=[6800])
    store = Store(tmp_path)
    job = store.new("t143-maker", SLEEP, tmp_path, min_ram_mb=2500)
    t = run(store, monitor(tmp_path, world), world, max_pause_s=0.2)
    until(lambda: (j := store.get(job.id)) is not None and j.state == WAITING
          and "reencolado_por_memoria" in names(store))
    assert world.free() == 7100                          # matarlo sí devolvió la memoria
    j = store.get(job.id)
    assert j.pauses == 0 and j.min_ram_mb == 9728        # 6 800 × 1,25 + 1 024, a 256
    rq = next(r for r in log(store) if r["event"] == "reencolado_por_memoria")
    assert rq["ram_trabajo_mb"] == 6800 and rq["ram_libre_mb"] == 300
    assert rq["pidio_mb"] == 2500 and rq["pide_mb"] == 9728 and rq["reencolado"] == 1
    assert "retiene el propio trabajo" in rq["motivo"]
    wait = next(r for r in log(store) if r["event"] == "esperando_margen")
    assert "pide 9728" in wait["motivos"]
    t.join(30)                                           # no espera para siempre
    j = store.get(job.id)
    assert j.state == FAILED and "sin margen para 9728 MB" in j.note
    assert names(store) == ["encolado", "arranca", "reencolado_por_memoria", "esperando_margen",
                            "termina", "pidio_menos_ram"]


def test_external_memory_pressure_pauses_at_most_twice_in_a_row(tmp_path):
    """Si la RAM la retiene otro, pausar puede servir; pero no sin límite: tras 2 pausas por
    memoria sin que corra tranquilo, la tercera vez se reencola."""
    world = World(base=8000, mems=[100], on_start=400)  # el trabajo no tiene la culpa
    store = Store(tmp_path)
    job = store.new("ligero", SLEEP, tmp_path)
    t = run(store, monitor(tmp_path, world), world, max_pause_s=0.2, resume_after_s=30)
    until(lambda: "reencolado_por_memoria" in names(store))
    store.cancel(job.id)
    t.join(30)
    ev = names(store)
    assert ev[:7] == ["encolado", "arranca", "pausa", "reanuda", "pausa", "reanuda",
                      "reencolado_por_memoria"]
    assert ev.count("pausa") == 2 and store.get(job.id).pauses == 2
    pause = next(r for r in log(store) if r["event"] == "pausa")
    assert pause["ram_trabajo_mb"] == 100 and "RAM libre 300" in pause["motivos"]
    rq = next(r for r in log(store) if r["event"] == "reencolado_por_memoria")
    assert rq["motivo"] == "2 pausas por memoria seguidas sin salida"


def test_requeues_go_on_while_it_learns_and_stop_when_it_does_not(tmp_path):
    """Se mata a mitad de crecer: mientras cada vez pida más, se reencola. Si dos veces seguidas
    no aprende nada (pide lo mismo), queda fallido diciendo cuánto pedir."""
    world = World(base=10_000, mems=[6800], bases=[10_000] * 3, on_start=7500)
    store = Store(tmp_path)
    job = store.new("igual", SLEEP, tmp_path, min_ram_mb=2500)
    run(store, monitor(tmp_path, world), world).join(30)
    j = store.get(job.id)
    assert j.state == FAILED and "--min-ram-mb 9728" in j.note
    assert names(store) == ["encolado", "arranca", "reencolado_por_memoria", "arranca",
                            "reencolado_por_memoria", "arranca", "cancelado_por_memoria",
                            "termina", "pidio_menos_ram"]
    hint = next(r for r in log(store) if r["event"] == "pidio_menos_ram")
    assert hint == {**hint, "pidio_mb": 2500, "pico_ram_mb": 6800, "sugerido_mb": 9728}


def test_a_job_that_keeps_growing_fails_once_it_would_not_fit(tmp_path):
    world = World(base=7100, mems=[6800, 9200, 12_200], bases=[10_000, 13_000, 13_000])
    store = Store(tmp_path)
    job = store.new("crece", SLEEP, tmp_path, min_ram_mb=2500)
    run(store, monitor(tmp_path, world), world).join(30)
    j = store.get(job.id)
    assert j.state == FAILED and "--min-ram-mb 16384 (el equipo tiene 16000)" in j.note
    assert [r.get("pide_mb") for r in log(store) if r["event"] == "reencolado_por_memoria"] == [
        9728, 12544]
    end = next(r for r in log(store) if r["event"] == "termina")
    assert end["pico_ram_mb"] == 12_200 and end["dur_s"] >= 0


def test_a_job_that_used_far_more_than_it_asked_is_recorded(tmp_path):
    world = World(base=12_000, mems=[3500])
    store = Store(tmp_path)
    job = store.new("corto", [sys.executable, "-c", "import time; time.sleep(0.3)"], tmp_path)
    run(store, monitor(tmp_path, world), world).join(30)
    assert store.get(job.id).state == DONE
    hint = next(r for r in log(store) if r["event"] == "pidio_menos_ram")
    assert (hint["pidio_mb"], hint["pico_ram_mb"], hint["sugerido_mb"]) == (0, 3500, 5632)
    # quien pide lo justo no deja aviso
    store2 = Store(tmp_path / "b")
    store2.new("justo", [sys.executable, "-c", "pass"], tmp_path, min_ram_mb=4096)
    w2 = World(12_000, [3500])
    run(store2, monitor(tmp_path, w2), w2).join(30)
    assert "pidio_menos_ram" not in names(store2)


def test_asking_more_ram_than_the_machine_has_fails_at_once(tmp_path):
    store = Store(tmp_path)
    job = store.new("enorme", [sys.executable, "-c", "pass"], tmp_path, min_ram_mb=20_000)
    world = World(12_000, [10])
    run(store, monitor(tmp_path, world), world).join(10)
    j = store.get(job.id)
    assert j.state == FAILED and j.started is None and "16000" in j.note


def test_guard_rules():
    g = mem.Guard(low_ram_mb=1024, calm_s=10)
    assert g.verdict(300, 6800, paused=False).startswith("la RAM la retiene")
    assert g.verdict(300, 400, paused=False) is None          # poco suyo: pausar puede ayudar
    assert g.verdict(300, 600, paused=False) is None          # sin él seguiría bajo el umbral
    g.paused_for_memory()
    g.paused_for_memory()
    assert g.verdict(300, 100, paused=True) is None           # a mitad de una pausa, no se corta
    assert g.verdict(300, 100, paused=False) == "2 pausas por memoria seguidas sin salida"
    g.observe(100, ram_low=False, paused=False, now=0)
    g.observe(100, ram_low=False, paused=False, now=10)       # 10 s corriendo sin apuro
    assert g.streak == 0 and g.peak == 100
    assert mem.ask_for(6800, 2500) == 9728 and mem.ask_for(100, 4096) == 4096
    assert mem.over_asked(3000, 2500, 2048) is None and mem.over_asked(7900, 2500, 2048) == 11008
