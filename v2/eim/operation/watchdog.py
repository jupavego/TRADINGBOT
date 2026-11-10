"""Vigilante de proceso: lanza la API con el servicio de operación y la relanza si cae.

Reinicia cuando el proceso termina, cuando el latido (`heartbeat.json`) no avanza en `stale_s`
(proceso colgado) o, si se le da una sonda, cuando el puerto deja de escuchar (T140). Espera
creciente entre reinicios (se reinicia la cuenta si el proceso aguantó más de `healthy_s`). Cada
reinicio queda en el registro estructurado y se avisa por notificación local. También vigila el
servicio de líderes (`eim.leaders supervise`).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from eim.observability import hooks_service
from eim.operation.alerts import CRITICAL, SERVICE, Alert
from eim.operation.notify import JsonLog, WindowsToast
from eim.operation.origin import stamp
from eim.operation.port_watch import GRACE_S, LOST_S, PortWatch, Probe


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
            tmp.write_text(json.dumps(stamp(row)), encoding="utf-8")
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


def _pump(source: IO[str], stream: str, tail: deque | None = None) -> None:
    """Copia cada línea a `sys.<stream>` con su hora UTC. Sin ella, el 2026-11-06 no se pudo fechar
    el fallo del socket (T140). Nunca deja de leer aunque no pueda escribir: si este hilo muriera,
    la tubería se llenaría y el servicio se quedaría parado al escribir en ella."""
    for line in source:
        if tail is not None:
            tail.append(line.rstrip())
        try:
            out = getattr(sys, stream)
            out.write(f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ} {line}")
            out.flush()
        except (OSError, ValueError):      # `UnicodeEncodeError` es un `ValueError`
            pass


def spawn_with_tail(cmd: list[str], env: dict[str, str], keep: int = 30,
                    stamp_stdout: bool = False) -> subprocess.Popen:
    """Lanza `cmd` copiando su stderr a la del vigilante, con hora, y guarda las últimas `keep`
    líneas en `proc.tail`: si el proceso cae a los segundos, el motivo queda en el registro (antes
    se perdía y el bucle de reinicios del 20-oct no dejó rastro).

    La salida estándar sigue heredada salvo con `stamp_stdout`, que es solo para la API (fechar sus
    peticiones): una tubería ata al hijo al hilo que la lee, y la captura no debe depender de eso.
    """
    proc = subprocess.Popen(cmd, env=env,  # noqa: S603
                            stdout=subprocess.PIPE if stamp_stdout else None,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    proc.tail = deque(maxlen=keep)  # type: ignore[attr-defined]
    threading.Thread(target=_pump, args=(proc.stderr, "stderr", proc.tail),  # type: ignore[attr-defined]
                     daemon=True).start()
    if stamp_stdout:
        threading.Thread(target=_pump, args=(proc.stdout, "stdout"), daemon=True).start()
    return proc


class Watchdog:
    def __init__(self, cmd: list[str], env: dict[str, str], heartbeat: Path, log: JsonLog,
                 stale_s: float = 900.0, check_s: float = 15.0, max_backoff_s: float = 300.0,
                 healthy_s: float = 600.0, spawn: Callable[..., subprocess.Popen] | None = None,
                 clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep,
                 notify: Callable[[Alert], None] | None = None,
                 title: str = "Servicio reiniciado", port_probe: Probe | None = None,
                 port_grace_s: float = GRACE_S, port_lost_s: float = LOST_S,
                 planned_rc: int | None = None,
                 on_planned: Callable[[], None] | None = None,
                 hold: Callable[[], str | None] | None = None) -> None:
        self.cmd, self.env, self.hb, self.log, self.title = cmd, env, heartbeat, log, title
        self.stale_s, self.check_s = stale_s, check_s
        self.max_backoff_s, self.healthy_s = max_backoff_s, healthy_s
        self._spawn = spawn or spawn_with_tail
        self._clock, self._sleep = clock, sleep
        self._notify = notify if notify is not None else WindowsToast()
        self.port_probe, self.port_grace_s, self.port_lost_s = port_probe, port_grace_s, port_lost_s
        self.restarts = 0
        # Salida pedida por el propio servicio (T128: compactar la base): no es una caída, no
        # avisa ni espera; se hace `on_planned` y se relanza.
        self.planned_rc, self.on_planned, self.planned = planned_rc, on_planned, 0
        self.last_rc: int | None = None
        # T120: mientras `hold()` dé un motivo (la unidad de datos no está), el proceso se detiene
        # y no se relanza; no es una caída: ni espera creciente ni aviso de reinicio.
        self.hold, self._held = hold, False

    def _stop(self, proc) -> None:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()

    def _watch(self, proc) -> str:
        """Bloquea hasta que el proceso muere, se cuelga o pierde el puerto; devuelve el motivo. Una
        lectura fallida del latido (archivo reemplazándose en Windows) no lo «detiene»: vale el
        último leído (T42-12: antes volvía al arranque y reiniciaba con un falso «latido
        detenido»). Sin `port_probe`, el puerto no se mira: hay servicios que no tienen."""
        last = self._clock()
        port = (PortWatch(self.port_probe, self.port_grace_s, self.port_lost_s, self._clock)
                if self.port_probe is not None else None)
        while True:
            self._sleep(self.check_s)
            rc = proc.poll()
            if rc is not None:
                self.last_rc = rc
                if self.hold is not None and (why := self.hold()):
                    self._held = True        # cayó porque se fue la unidad: no es una caída
                    return why
                return f"el proceso terminó (código {rc})"
            if (hb := heartbeat_t(self.hb)) is not None:
                last = max(last, hb / 1000)
            if self._clock() - last > self.stale_s:
                self._stop(proc)
                return f"latido detenido {self._clock() - last:.0f} s"
            if port is not None and (why := port.check()):
                self._stop(proc)
                return why
            if self.hold is not None and (why := self.hold()):
                self._stop(proc)
                self._held = True
                return why

    def _wait_hold(self) -> None:
        """Espera sin relanzar mientras `hold()` dé motivo; una línea al pausar y otra al volver."""
        why = self.hold() if self.hold is not None else None
        if not why:
            return
        t0 = self._clock()
        self.log.write("en_pausa", "warn", reason=why)
        hooks_service.service_event("operation.watchdog", "en pausa", status="error",
                                    detail={"reason": why, "service": self.title})
        while self.hold():
            self._sleep(self.check_s)
        self.log.write("reanudado", pausa_s=round(self._clock() - t0, 1))

    def _planned_restart(self) -> None:
        self.planned += 1
        self.log.write("reinicio_planificado", code=self.last_rc, veces=self.planned)
        if self.on_planned is None:
            return
        try:
            self.on_planned()
        except Exception as exc:  # noqa: BLE001 - el mantenimiento nunca impide relanzar
            self.log.write("mantenimiento_fallido", "error", error=f"{type(exc).__name__}: {exc}")

    def run(self, max_starts: int | None = None) -> None:
        fails, n = 0, 0
        while max_starts is None or n < max_starts:
            n += 1
            self._wait_hold()
            t0 = self._clock()
            self.last_rc = None
            self.log.write("proceso_lanzado", cmd=" ".join(self.cmd), intento=n)
            proc = self._spawn(self.cmd, self.env)
            try:
                why = self._watch(proc)
            except KeyboardInterrupt:
                proc.terminate()
                self.log.write("vigilante_detenido", reason="interrupción del usuario")
                return
            if self.planned_rc is not None and self.last_rc == self.planned_rc:
                self._planned_restart()
                continue
            if self._held:
                self._held = False
                continue
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
