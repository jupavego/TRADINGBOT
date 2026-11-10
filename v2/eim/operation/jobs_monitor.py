"""Qué mira la cola de trabajos pesados antes de arrancar y mientras corre (T127, T149).

Separado de `jobs.py` para que el ejecutor quepa en 300 líneas; `jobs` lo reexporta.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from eim.data.collectors.health import STALE_S
from eim.operation import usage_win
from eim.operation.jobs_store import Job

ADMIT_RAM_MB, LOW_RAM_MB, ADMIT_CPU = 2048, 1024, 80.0
QUEUE_MAX, BACKLOG_MAX = 1000, 200


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


def _ram_total_mb() -> int:
    if usage_win.supported():
        return int(usage_win.memory()["ram_total_mb"])
    return 1 << 20


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
    """`pressure()` deja en `ram_free` la última lectura y en `ram_low` si la RAM era motivo."""

    def __init__(self, data_dir: Path, ram: Callable[[], int] = _ram_free_mb,
                 cpu: Callable[[], float] | None = None,
                 ram_total: Callable[[], int] = _ram_total_mb) -> None:
        self.hb = Path(data_dir) / "micro_hft" / "heartbeat.json"
        self.ram, self.cpu, self.ram_total = ram, cpu or _Cpu(), ram_total
        self.prev: dict | None = None
        self.ram_free, self.ram_low = 1 << 20, False

    def pressure(self) -> list[str]:
        try:
            hb = json.loads(self.hb.read_text("utf-8"))
        except (OSError, ValueError):
            hb = None
        out, self.prev = capture_pressure(hb, self.prev, time.time())
        self.ram_free = ram = self.ram()
        self.ram_low = ram < LOW_RAM_MB
        if self.ram_low:
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
