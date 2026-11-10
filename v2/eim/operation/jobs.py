"""Cola de trabajos pesados (T127, entregable 2). Ejecuta un trabajo a la vez y solo con margen,
lo pausa si la captura HFT sufre y lo reanuda cuando se recupera.

    python -m eim.operation.jobs submit --name gate -- python -m pytest -q
    python -m eim.operation.jobs list
    python -m eim.operation.jobs cancel <id>

`submit` encola, espera a que termine su trabajo y devuelve su código de salida. Si no hay
ejecutor (cerrojo `data/jobs/runner.lock`), lo hace él y vacía la cola entera; si lo hay,
espera su turno y toma el relevo si aquel muere. El trabajo corre en IDLE (`--tier batch`) o
BELOW_NORMAL (`service`), con todo su árbol en un objeto de Windows (`jobs_proc.py`).

- **Admisión:** RAM libre ≥ 2 GB (o lo que pida `--min-ram-mb`), CPU del equipo ≤ 80 % y
  ninguna presión en la captura. Si pide más RAM de la que tiene el equipo, falla sin esperar.
- **Presión (pausa):** cola de la captura > 1 000 mensajes o escritura atrasada > 200, huecos o
  descartes nuevos, reinicio de la captura, o RAM libre < 1 GB.
- **Reanudación:** tras 90 s sin presión. Si la presión dura más de 15 min con el trabajo
  pausado, no viene de él y se reanuda igual.
- **Memoria propia (T149, `jobs_memory.py`):** si la RAM que falta la retiene el trabajo, pausarlo
  no sirve: se mata y vuelve a la cola pidiendo su pico. El registro dice su memoria y si pidió
  menos de la que usó.
- No cuentan un latido de la captura de más de 2 min (captura parada, o sin captura en este
  equipo: no hay nada que proteger) ni la CPU: con el trabajo en IDLE el equipo siempre parece
  lleno.
- **Repetir tras una pausa** (`--retry-paused N`, T116): en la pausa caducan los plazos de reloj
  del trabajo (120 s de plazo, 185 s congelado); si falla tras pausas se repite (el gate, con 1).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path

from eim.operation import jobs_memory as mem
from eim.operation.jobs_monitor import (  # noqa: F401 - reexportados: la cola se usa desde aquí
    ADMIT_CPU,
    ADMIT_RAM_MB,
    LOW_RAM_MB,
    Monitor,
    capture_pressure,
)
from eim.operation.jobs_proc import JobProcess
from eim.operation.jobs_store import (
    CANCELLED,
    DONE,
    FAILED,
    FINAL,
    INTERRUPTED,
    PAUSED,
    PENDING,
    RUNNING,
    WAITING,
    Job,
    Store,
)
from eim.operation.watchdog import instance_lock

POLL_S, RESUME_AFTER_S, MAX_PAUSE_S = 5.0, 90.0, 900.0
MEM_EVERY = 6                              # memoria del trabajo cada 30 s, o siempre si falta RAM


def _say(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class Runner:
    def __init__(self, store: Store, monitor: Monitor, poll_s: float = POLL_S,
                 resume_after_s: float = RESUME_AFTER_S, max_pause_s: float = MAX_PAUSE_S,
                 say: Callable[[str], None] = _say, spawn: type[JobProcess] = JobProcess) -> None:
        self.store, self.monitor, self.poll_s = store, monitor, poll_s
        self.resume_after_s, self.max_pause_s, self.say = resume_after_s, max_pause_s, say
        self.spawn = spawn
        self.requeues: dict[str, int] = {}               # por trabajo, mientras viva el ejecutor
        self.peaks: dict[str, float] = {}
        self.stuck: dict[str, int] = {}                  # reencolados seguidos sin pedir más
        self.deadline: dict[str, float] = {}             # tope de espera tras reencolarlo
        self.asked: dict[str, int] = {}                  # lo que pidió al encolarlo

    def log(self, job: Job, what: str, **detail) -> None:
        self.store.save(job)
        self.store.event(job, what, **detail)
        extra = "; ".join(f"{k}: {v}" for k, v in detail.items())
        self.say(f"[{time.strftime('%H:%M:%S', time.gmtime())} UTC] {job.name}: {what}"
                 + (f" ({extra})" if extra else ""))

    def drain(self) -> None:
        for j in self.store.all():                       # restos de un ejecutor que murió
            if j.state in (RUNNING, PAUSED):
                j.state, j.ended, j.note = INTERRUPTED, time.time(), "murió el ejecutor anterior"
                self.log(j, "interrumpido")
        while (job := self.store.next_pending()) is not None:
            self.run_one(job)

    def finish(self, job: Job, state: str, rc: int | None) -> None:
        job.state, job.rc, job.ended = state, rc, time.time()
        dur = round(job.ended - (job.started or job.ended), 1)
        peak = self.peaks.get(job.id, 0.0)
        self.log(job, "termina", estado=state, rc=rc, dur_s=dur, pausas=job.pauses,
                 pausado_s=round(job.paused_s, 1), pico_ram_mb=peak)
        asked = self.asked.get(job.id, job.min_ram_mb)
        if (hint := mem.over_asked(peak, asked, ADMIT_RAM_MB)) is not None:
            self.log(job, "pidio_menos_ram", pidio_mb=asked, pico_ram_mb=peak,
                     sugerido_mb=hint)

    def admit(self, job: Job) -> bool:
        last = None
        if job.min_ram_mb > (total := self.monitor.ram_total()):
            job.note = f"pide {job.min_ram_mb} MB de RAM y el equipo tiene {total}"
            self.finish(job, FAILED, None)
            return False
        while True:
            if self.store.cancelled(job):
                self.finish(job, CANCELLED, None)
                return False
            if time.time() > self.deadline.get(job.id, float("inf")):
                job.note = (f"sin margen para {job.min_ram_mb} MB en "
                            f"{mem.REQUEUE_WAIT_S / 3600:.0f} h tras reencolarlo")
                self.finish(job, FAILED, None)
                return False
            if not (why := self.monitor.admission(job)):
                return True
            if why != last:
                job.state, last = WAITING, why
                self.log(job, "esperando_margen", motivos=", ".join(why))
            time.sleep(self.poll_s)

    def run_one(self, job: Job) -> None:
        self.asked.setdefault(job.id, job.min_ram_mb)
        if not self.admit(job):
            return
        try:
            proc = self.spawn(job.cmd, Path(job.cwd), self.store.out_path(job), job.tier)
        except (OSError, ValueError) as e:
            job.note = f"{type(e).__name__}: {e}"
            self.finish(job, FAILED, None)
            return
        self.deadline.pop(job.id, None)
        job.state, job.started = RUNNING, job.started or time.time()   # primera vez que arrancó
        self.log(job, "arranca", pid=proc.pid, nivel=job.tier, pide_mb=job.min_ram_mb)
        try:
            rc = self.watch(job, proc)
        except mem.Requeue as rq:
            proc.kill()
            self.requeue(job, rq)
            return
        except BaseException:
            proc.kill()
            self.finish(job, INTERRUPTED, None)
            raise
        finally:
            proc.close()
        if rc is not None:
            self.finish(job, DONE if rc == 0 else FAILED, rc)

    def requeue(self, job: Job, rq: mem.Requeue) -> None:
        """Pausarlo no liberaba nada: muerto, vuelve a la cola pidiendo lo que de verdad usa."""
        n = self.requeues[job.id] = self.requeues.get(job.id, 0) + 1
        peak, asked = self.peaks.get(job.id, 0.0), self.asked.get(job.id, job.min_ram_mb)
        need = mem.ask_for(peak, job.min_ram_mb)
        # Muere a mitad de crecer: mientras pida más, aprende; sin crecer, el tope.
        stuck = self.stuck[job.id] = 0 if need > job.min_ram_mb else self.stuck.get(job.id, 0) + 1
        detail = {"motivo": rq.why, "ram_trabajo_mb": rq.job_ram_mb,
                  "ram_libre_mb": rq.ram_free_mb, "pico_ram_mb": peak, "pidio_mb": asked}
        total = self.monitor.ram_total()
        if stuck >= mem.MAX_REQUEUES or need > total:
            job.note = (f"cancelado {n} veces por retener la RAM que lo pausaba; pide "
                        f"--min-ram-mb {need}" + (f" (el equipo tiene {total})"
                                                  if need > total else ""))
            self.log(job, "cancelado_por_memoria", **detail)
            self.finish(job, FAILED, None)
            return
        job.state, job.min_ram_mb, job.created = PENDING, need, time.time()   # al final de la cola
        self.deadline[job.id] = time.time() + mem.REQUEUE_WAIT_S
        self.log(job, "reencolado_por_memoria", **detail, pide_mb=need, reencolado=n)

    def watch(self, job: Job, proc: JobProcess) -> int | None:
        """Vigila el trabajo hasta que termina; None si se canceló. Lanza `Requeue` si pausarlo
        no sirve porque la RAM que falta la retiene él (T149)."""
        paused_at = calm_since = None
        guard, polls, own = mem.Guard(LOW_RAM_MB, self.resume_after_s), 0, 0.0
        while (rc := proc.poll()) is None:
            if self.store.cancelled(job):
                proc.kill()
                self.finish(job, CANCELLED, proc.poll())
                return None
            why, now = self.monitor.pressure(), time.monotonic()
            low, free = self.monitor.ram_low, self.monitor.ram_free
            if low or polls % MEM_EVERY == 0:      # medirlo enumera todos los procesos
                own = proc.memory_mb()
            polls += 1
            guard.observe(own, low, paused_at is not None, now)
            self.peaks[job.id] = max(self.peaks.get(job.id, 0.0), guard.peak)
            if low and (verdict := guard.verdict(free, own, paused_at is not None)):
                if paused_at is not None:
                    job.paused_s += now - paused_at
                raise mem.Requeue(verdict, own, free)
            calm_since = None if why else (calm_since or now)
            if why and paused_at is None:
                proc.suspend()
                paused_at, job.state, job.pauses = now, PAUSED, job.pauses + 1
                if low:
                    guard.paused_for_memory()
                self.log(job, "pausa", motivos=", ".join(why), ram_trabajo_mb=own)
            elif paused_at is not None and (
                    (calm_since is not None and now - calm_since >= self.resume_after_s)
                    or now - paused_at >= self.max_pause_s):
                proc.resume()
                job.paused_s, job.state = job.paused_s + now - paused_at, RUNNING
                self.log(job, "reanuda", tras_s=round(now - paused_at, 1), motivo=(
                    "sin presión" if calm_since is not None else
                    "la presión sigue con el trabajo pausado: no viene de él"))
                paused_at = None
            time.sleep(self.poll_s)
        return rc


def submit(data_dir: Path, name: str, cmd: list[str], cwd: Path, tier: str = "batch",
           min_ram_mb: int = 0, monitor: Monitor | None = None, poll_s: float = POLL_S,
           say: Callable[[str], None] = _say, retry_paused: int = 0,
           resume_after_s: float = RESUME_AFTER_S) -> int:
    for attempt in range(retry_paused + 1):
        rc, j = _submit_once(data_dir, name, cmd, cwd, tier, min_ram_mb, monitor, poll_s, say,
                             resume_after_s)
        if rc == 0 or j is None or not j.pauses or attempt == retry_paused:
            return rc
        say(f"{name} falló tras {j.pauses} pausa(s) de la cola ({j.paused_s:.0f} s congelado): "
            "un plazo de reloj pudo caducar durante la pausa; se repite.")
    return rc


def _submit_once(data_dir: Path, name: str, cmd: list[str], cwd: Path, tier: str,
                 min_ram_mb: int, monitor: Monitor | None, poll_s: float,
                 say: Callable[[str], None], resume_after_s: float) -> tuple[int, Job | None]:
    store = Store(data_dir)
    store.prune(time.time())
    job = store.new(name, cmd, cwd, tier, min_ram_mb)
    say(f"Trabajo {job.id} en cola; salida en {store.out_path(job)}")
    while True:
        if (lock := instance_lock(store.root / "runner.lock")) is not None:
            try:
                Runner(store, monitor or Monitor(data_dir), poll_s, resume_after_s, say=say).drain()
            finally:
                lock.close()
        if (j := store.get(job.id)) is None or j.state in FINAL:
            break
        time.sleep(min(poll_s, 2.0))
    if j is None:
        say("El trabajo desapareció de la cola.")
        return 3, None
    tail = store.out_path(j).read_text("utf-8", errors="replace").splitlines()[-15:]
    say("\n".join(tail))
    return (j.rc if j.rc is not None else (130 if j.state == CANCELLED else 3)), j


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eim.operation.jobs", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit", help="encola una orden y espera a que termine")
    s.add_argument("--name", required=True)
    s.add_argument("--tier", choices=("batch", "service"), default="batch")
    s.add_argument("--cwd", default=".")
    s.add_argument("--min-ram-mb", type=int, default=0)
    s.add_argument("--retry-paused", type=int, default=0,
                   help="repite hasta N veces si falla tras una pausa (el gate: 1)")
    s.add_argument("command", nargs=argparse.REMAINDER, help="-- orden y argumentos")
    sub.add_parser("list", help="trabajos recientes")
    c = sub.add_parser("cancel", help="cancela un trabajo en cola o en marcha")
    c.add_argument("id")
    a = ap.parse_args(argv)
    store = Store(Path(a.data_dir))
    if a.cmd == "submit":
        cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
        if not cmd:
            ap.error("falta la orden: submit --name N -- <orden> [args]")
        return submit(Path(a.data_dir), a.name, cmd, Path(a.cwd), a.tier, a.min_ram_mb,
                      retry_paused=a.retry_paused)
    if a.cmd == "cancel":
        ok = store.cancel(a.id)
        print("cancelación pedida" if ok else "no está en cola ni en marcha")
        return 0 if ok else 1
    for j in store.all()[-30:]:
        dur = "" if j.started is None else f"{(j.ended or time.time()) - j.started:7.0f} s"
        print(f"{j.id:40} {j.state:17} {dur:>9} pausas={j.pauses} rc={j.rc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
