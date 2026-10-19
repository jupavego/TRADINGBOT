"""Vigilante de proceso: lanza la API con el servicio de operación y la relanza si cae.

Reinicia cuando el proceso termina o cuando el latido (`heartbeat.json`) no avanza en
`stale_s` (proceso colgado). Espera creciente entre reinicios (se reinicia la cuenta si el
proceso aguantó más de `healthy_s`). Cada reinicio queda en el registro estructurado y se
avisa por notificación local. También vigila el servicio de líderes (`eim.leaders supervise`).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO

from eim.observability import hooks_service
from eim.operation.alerts import CRITICAL, SERVICE, Alert
from eim.operation.notify import JsonLog, WindowsToast


def heartbeat_t(path: Path) -> int | None:
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["last_heartbeat"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def instance_lock(path: Path) -> IO[bytes] | None:
    """Cerrojo de instancia única sobre `path`; None si otro proceso lo tiene. El sistema lo
    suelta al morir el proceso (no quedan cerrojos huérfanos): mantener el objeto abierto."""
    path.parent.mkdir(parents=True, exist_ok=True)
    f = path.open("a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


class Watchdog:
    def __init__(self, cmd: list[str], env: dict[str, str], heartbeat: Path, log: JsonLog,
                 stale_s: float = 900.0, check_s: float = 15.0, max_backoff_s: float = 300.0,
                 healthy_s: float = 600.0, spawn: Callable[..., subprocess.Popen] | None = None,
                 clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep,
                 notify: Callable[[Alert], None] | None = None,
                 title: str = "Servicio reiniciado") -> None:
        self.cmd, self.env, self.hb, self.log, self.title = cmd, env, heartbeat, log, title
        self.stale_s, self.check_s = stale_s, check_s
        self.max_backoff_s, self.healthy_s = max_backoff_s, healthy_s
        self._spawn = spawn or (lambda cmd, env: subprocess.Popen(cmd, env=env))  # noqa: S603
        self._clock, self._sleep = clock, sleep
        self._notify = notify if notify is not None else WindowsToast()
        self.restarts = 0

    def _watch(self, proc) -> str:
        """Bloquea hasta que el proceso muere o se cuelga; devuelve el motivo."""
        started = self._clock()
        while True:
            self._sleep(self.check_s)
            rc = proc.poll()
            if rc is not None:
                return f"el proceso terminó (código {rc})"
            hb = heartbeat_t(self.hb)
            last = max(started, hb / 1000 if hb else 0.0)
            if self._clock() - last > self.stale_s:
                proc.terminate()
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return f"latido detenido {self._clock() - last:.0f} s"

    def run(self, max_starts: int | None = None) -> None:
        fails, n = 0, 0
        while max_starts is None or n < max_starts:
            n += 1
            t0 = self._clock()
            self.log.write("proceso_lanzado", cmd=" ".join(self.cmd), intento=n)
            proc = self._spawn(self.cmd, self.env)
            try:
                why = self._watch(proc)
            except KeyboardInterrupt:
                proc.terminate()
                self.log.write("vigilante_detenido", reason="interrupción del usuario")
                return
            fails = 0 if self._clock() - t0 >= self.healthy_s else fails + 1
            wait = min(self.max_backoff_s, 5.0 * 2 ** fails)
            self.restarts += 1
            self.log.write("proceso_reiniciado", "error", reason=why, retry_s=wait,
                           restarts=self.restarts)
            hooks_service.service_event("operation.watchdog", "proceso reiniciado",
                                        status="error", detail={
                                            "reason": why, "retry_s": wait,
                                            "restarts": self.restarts, "service": self.title})
            try:
                self._notify(Alert(int(self._clock() * 1000), SERVICE, CRITICAL,
                                   self.title, f"{why}; se relanza en {wait:.0f} s",
                                   SERVICE))
            except Exception:  # noqa: BLE001, S110 - el aviso nunca frena el reinicio
                pass
            self._sleep(wait)
