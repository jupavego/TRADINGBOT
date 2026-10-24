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
import threading
import time
from collections import deque
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


def write_heartbeat(path: Path, row: dict, attempts: int = 3, delay_s: float = 0.05,
                    sleep: Callable[[float], None] = time.sleep) -> OSError | None:
    """Escritura atómica del latido (temporal + `replace`): None si quedó escrito; si no, el
    último error (no lanza). En Windows `replace` falla con WinError 5 si otro proceso está
    leyendo el archivo (el vigilante, una copia): se reintenta `attempts` veces cada `delay_s`.
    El 2026-10-24 un fallo así, sin reintento ni captura, detuvo el bucle de operación 9 min."""
    tmp, err = path.with_suffix(".tmp"), None
    for i in range(attempts):
        if i:
            sleep(delay_s)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(row), encoding="utf-8")
            tmp.replace(path)
            return None
        except OSError as e:
            err = e
    return err


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


def spawn_with_tail(cmd: list[str], env: dict[str, str], keep: int = 30) -> subprocess.Popen:
    """Lanza `cmd` copiando su stderr a la del vigilante (sin cambiar lo que ya se ve) y guarda
    las últimas `keep` líneas en `proc.tail`: si el proceso cae a los segundos, el motivo queda en
    el registro (antes se perdía y el bucle de reinicios del 20-oct no dejó rastro)."""
    proc = subprocess.Popen(cmd, env=env, stderr=subprocess.PIPE,  # noqa: S603
                            text=True, encoding="utf-8", errors="replace")
    proc.tail = deque(maxlen=keep)  # type: ignore[attr-defined]

    def pump() -> None:
        for line in proc.stderr:  # type: ignore[union-attr]
            proc.tail.append(line.rstrip())  # type: ignore[attr-defined]
            sys.stderr.write(line)
            sys.stderr.flush()

    threading.Thread(target=pump, daemon=True).start()
    return proc


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
        self._spawn = spawn or spawn_with_tail
        self._clock, self._sleep = clock, sleep
        self._notify = notify if notify is not None else WindowsToast()
        self.restarts = 0

    def _watch(self, proc) -> str:
        """Bloquea hasta que el proceso muere o se cuelga; devuelve el motivo. Una lectura fallida
        del latido (archivo reemplazándose en Windows) no lo «detiene»: vale el último leído
        (T42-12: antes volvía al arranque y reiniciaba con un falso «latido detenido»)."""
        last = self._clock()
        while True:
            self._sleep(self.check_s)
            rc = proc.poll()
            if rc is not None:
                return f"el proceso terminó (código {rc})"
            if (hb := heartbeat_t(self.hb)) is not None:
                last = max(last, hb / 1000)
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
            tail = list(getattr(proc, "tail", ()))[-8:]
            self.log.write("proceso_reiniciado", "error", reason=why, retry_s=wait,
                           restarts=self.restarts, stderr_tail=" | ".join(tail)[-1500:])
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
