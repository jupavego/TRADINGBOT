"""Cola de trabajos pesados en disco (T127): un JSON por trabajo y un registro por día.

`data/jobs/queue/<id>.json` guarda el trabajo y su estado. Lo escribe solo el ejecutor, salvo
al encolarlo, y siempre de forma atómica (archivo temporal + reemplazo). La cancelación es un
archivo aparte, `<id>.cancel`, para no pisar al ejecutor. `data/jobs/log/AAAA-MM-DD.jsonl`
anota cada paso y `data/jobs/out/<id>.log` recoge la salida del trabajo.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

PENDING, WAITING, RUNNING, PAUSED = "en_cola", "esperando_margen", "corriendo", "pausado"
DONE, FAILED, CANCELLED, INTERRUPTED = "hecho", "fallido", "cancelado", "interrumpido"
ACTIVE = (PENDING, WAITING, RUNNING, PAUSED)
FINAL = (DONE, FAILED, CANCELLED, INTERRUPTED)
KEEP_DAYS = 14


@dataclass
class Job:
    id: str
    name: str
    cmd: list[str]
    cwd: str
    tier: str = "batch"
    min_ram_mb: int = 0
    state: str = PENDING
    created: float = field(default_factory=time.time)
    started: float | None = None
    ended: float | None = None
    rc: int | None = None
    pauses: int = 0
    paused_s: float = 0.0
    note: str = ""


def _ts(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class Store:
    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir) / "jobs"
        self.queue, self.logs, self.out = (self.root / d for d in ("queue", "log", "out"))

    def new(self, name: str, cmd: list[str], cwd: Path, tier: str = "batch",
            min_ram_mb: int = 0) -> Job:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:40] or "trabajo"
        job = Job(f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{safe}-{secrets.token_hex(2)}",
                  name, list(cmd), str(Path(cwd).resolve()), tier, min_ram_mb)
        self.save(job)
        self.event(job, "encolado", cmd=" ".join(cmd), tier=tier)
        return job

    def save(self, job: Job) -> None:
        self.queue.mkdir(parents=True, exist_ok=True)
        tmp = self.queue / f"{job.id}.json.tmp"
        tmp.write_text(json.dumps(asdict(job), ensure_ascii=False, indent=1), encoding="utf-8")
        for attempt in range(100):           # Windows niega el reemplazo mientras otro lo lee
            try:
                os.replace(tmp, self.queue / f"{job.id}.json")
                return
            except PermissionError:
                if attempt == 99:
                    raise
                time.sleep(0.02)

    def get(self, job_id: str) -> Job | None:
        path = self.queue / f"{job_id}.json"
        for attempt in range(10):            # Windows: la lectura choca con un reemplazo
            try:
                return Job(**json.loads(path.read_text("utf-8")))
            except FileNotFoundError:
                return None
            except (OSError, ValueError, TypeError):
                if attempt == 9:
                    return None
                time.sleep(0.02)
        return None

    def all(self) -> list[Job]:
        out = []
        for f in self.queue.glob("*.json") if self.queue.exists() else []:
            if (j := self.get(f.stem)) is not None:
                out.append(j)
        return sorted(out, key=lambda j: (j.created, j.id))

    def next_pending(self) -> Job | None:
        return next((j for j in self.all() if j.state in (PENDING, WAITING)), None)

    def cancel(self, job_id: str) -> bool:
        if (j := self.get(job_id)) is None or j.state in FINAL:
            return False
        (self.queue / f"{job_id}.cancel").write_text(_ts(time.time()), encoding="utf-8")
        return True

    def cancelled(self, job: Job) -> bool:
        return (self.queue / f"{job.id}.cancel").exists()

    def out_path(self, job: Job) -> Path:
        self.out.mkdir(parents=True, exist_ok=True)
        return self.out / f"{job.id}.log"

    def event(self, job: Job, what: str, **detail) -> dict:
        now = time.time()
        rec = {"t": int(now * 1000), "ts": _ts(now), "job": job.id, "name": job.name,
               "event": what, **detail}
        self.logs.mkdir(parents=True, exist_ok=True)
        with (self.logs / f"{rec['ts'][:10]}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def prune(self, now_s: float, keep_days: int = KEEP_DAYS) -> int:
        """Borra trabajos terminados, su salida y los registros de más de `keep_days`."""
        cut, n = now_s - keep_days * 86400, 0
        for j in self.all():
            if j.state in FINAL and (j.ended or j.created) < cut:
                for p in (self.queue / f"{j.id}.json", self.queue / f"{j.id}.cancel",
                          self.out / f"{j.id}.log"):
                    p.unlink(missing_ok=True)
                n += 1
        for f in self.logs.glob("????-??-??.jsonl") if self.logs.exists() else []:
            if f.stem < _ts(cut)[:10]:
                f.unlink(missing_ok=True)
        return n
