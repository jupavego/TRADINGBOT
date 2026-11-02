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
  ninguna presión en la captura.
- **Presión (pausa):** cola de la captura > 1 000 mensajes o escritura atrasada > 200, huecos o
  descartes nuevos, reinicio de la captura, o RAM libre < 1 GB.
- **Reanudación:** tras 90 s sin presión. Si la presión dura más de 15 min con el trabajo
  pausado, no viene de él y se reanuda igual.
- No cuentan un latido de la captura de más de 2 min (captura parada, o sin captura en este
  equipo: no hay nada que proteger) ni la CPU: con el trabajo en IDLE el equipo siempre parece
  lleno.
- **Repetir tras una pausa** (`--retry-paused N`, T116): en la pausa caducan los plazos de reloj
  del trabajo (120 s de plazo, 185 s congelado); si falla tras pausas se repite (el gate, con 1).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

from eim.data.collectors.health import STALE_S
from eim.operation import usage_win
from eim.operation.jobs_proc import JobProcess
from eim.operation.jobs_store import (
    CANCELLED,
    DONE,
    FAILED,
    FINAL,
    INTERRUPTED,
    PAUSED,
    RUNNING,
    WAITING,
    Job,
    Store,
)
from eim.operation.watchdog import instance_lock

ADMIT_RAM_MB, LOW_RAM_MB, ADMIT_CPU = 2048, 1024, 80.0
QUEUE_MAX, BACKLOG_MAX = 1000, 200
POLL_S, RESUME_AFTER_S, MAX_PAUSE_S = 5.0, 90.0, 900.0


def _say(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def capture_pressure(hb: dict | None, prev: dict | None,
                     now_s: float) -> tuple[list[str], dict | None]:
    """Motivos de presión en la captura HFT según su latido, frente a la lectura anterior."""
    if not hb or now_s - (hb.get("last_heartbeat") or 0) / 1000 > STALE_S:
        return [], None
    cur = {"run": hb.get("started_at"), "gaps": sum((hb.get("gaps") or {}).values()),
           "dropped": (hb.get("dropped") or 0) + (hb.get("pending_dropped") or 0)}
    out = []
    if (q := hb.get("queue") or 0) > QUEUE_MAX:
        out.append(f"cola de la captura en {q} mensajes")
    if (b := hb.get("write_backlog") or 0) > BACKLOG_MAX:
        out.append(f"escritura de la captura atrasada ({b})")
    if prev is not None and prev["run"] != cur["run"]:
        out.append("la captura se reinició")
    elif prev is not None:
        if cur["gaps"] > prev["gaps"]:
            out.append(f"{cur['gaps'] - prev['gaps']} huecos nuevos en la captura")
        if cur["dropped"] > prev["dropped"]:
            out.append(f"{cur['dropped'] - prev['dropped']} mensajes descartados")
    return out, cur


def _ram_free_mb() -> int:
    if usage_win.supported():
        return int(usage_win.memory()["ram_free_mb"])
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 1 << 20                       # sin dato: la RAM no frena


class _Cpu:
    """CPU del equipo desde la llamada anterior (Windows; fuera, 0)."""

    def __init__(self) -> None:
        self.prev = usage_win.system_times() if usage_win.supported() else None

    def __call__(self) -> float:
        if self.prev is None:
            return 0.0
        busy, total = usage_win.system_times()
        b0, t0 = self.prev
        self.prev = (busy, total)
        return 100 * (busy - b0) / (total - t0) if total > t0 else 0.0


class Monitor:
    def __init__(self, data_dir: Path, ram: Callable[[], int] = _ram_free_mb,
                 cpu: Callable[[], float] | None = None) -> None:
        self.hb = Path(data_dir) / "micro_hft" / "heartbeat.json"
        self.ram, self.cpu = ram, cpu or _Cpu()
        self.prev: dict | None = None

    def pressure(self) -> list[str]:
        try:
            hb = json.loads(self.hb.read_text("utf-8"))
        except (OSError, ValueError):
            hb = None
        out, self.prev = capture_pressure(hb, self.prev, time.time())
        if (ram := self.ram()) < LOW_RAM_MB:
            out.append(f"RAM libre {ram} MB")
        return out

    def admission(self, job: Job) -> list[str]:
        out = self.pressure()
        need = max(ADMIT_RAM_MB, job.min_ram_mb)
        if (ram := self.ram()) < need and ram >= LOW_RAM_MB:
            out.append(f"RAM libre {ram} MB (pide {need})")
        if (cpu := self.cpu()) > ADMIT_CPU:
            out.append(f"CPU del equipo al {cpu:.0f} %")
        return out


class Runner:
    def __init__(self, store: Store, monitor: Monitor, poll_s: float = POLL_S,
                 resume_after_s: float = RESUME_AFTER_S, max_pause_s: float = MAX_PAUSE_S,
                 say: Callable[[str], None] = _say) -> None:
        self.store, self.monitor, self.poll_s = store, monitor, poll_s
        self.resume_after_s, self.max_pause_s, self.say = resume_after_s, max_pause_s, say

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
        self.log(job, "termina", estado=state, rc=rc, dur_s=dur, pausas=job.pauses,
                 pausado_s=round(job.paused_s, 1))

    def admit(self, job: Job) -> bool:
        last = None
        while True:
            if self.store.cancelled(job):
                self.finish(job, CANCELLED, None)
                return False
            if not (why := self.monitor.admission(job)):
                return True
            if why != last:
                job.state, last = WAITING, why
                self.log(job, "esperando_margen", motivos=", ".join(why))
            time.sleep(self.poll_s)

    def run_one(self, job: Job) -> None:
        if not self.admit(job):
            return
        try:
            proc = JobProcess(job.cmd, Path(job.cwd), self.store.out_path(job), job.tier)
        except (OSError, ValueError) as e:
            job.note = f"{type(e).__name__}: {e}"
            self.finish(job, FAILED, None)
            return
        job.state, job.started = RUNNING, time.time()
        self.log(job, "arranca", pid=proc.pid, nivel=job.tier)
        try:
            rc = self.watch(job, proc)
        except BaseException:
            proc.kill()
            self.finish(job, INTERRUPTED, None)
            raise
        finally:
            proc.close()
        if rc is not None:
            self.finish(job, DONE if rc == 0 else FAILED, rc)

    def watch(self, job: Job, proc: JobProcess) -> int | None:
        """Vigila el trabajo hasta que termina; None si se canceló."""
        paused_at = calm_since = None
        while (rc := proc.poll()) is None:
            if self.store.cancelled(job):
                proc.kill()
                self.finish(job, CANCELLED, proc.poll())
                return None
            why, now = self.monitor.pressure(), time.monotonic()
            calm_since = None if why else (calm_since or now)
            if why and paused_at is None:
                proc.suspend()
                paused_at, job.state, job.pauses = now, PAUSED, job.pauses + 1
                self.log(job, "pausa", motivos=", ".join(why))
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
