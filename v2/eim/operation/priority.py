"""Prioridad de los procesos del EIM por nivel (T126, fase 1).

En el equipo de 4 núcleos, un trabajo pesado (gate, copia, auditoría, un LLM local) que compite
de igual a igual con la captura en vivo le roba la CPU: de ahí los silencios de 3–6 s de T78. Y
la tarea programada lanzaba todo en BELOW_NORMAL (prioridad 7), así que la captura quedaba por
DEBAJO de cualquier programa abierto. Cada proceso declara su papel (el mismo nombre que pasa a
`observability.emit.configure`) y aquí se traduce a una clase de prioridad. Orden buscado: la
captura por encima de todo; los programas del usuario (NORMAL) por encima de los servicios del
EIM, para que el equipo siga respondiendo; lo pesado, al fondo.

| nivel      | clase de Windows | quién                                                        |
|------------|------------------|--------------------------------------------------------------|
| `realtime` | ABOVE_NORMAL     | recolectores en vivo (microestructura, HFT, liquidaciones)    |
| `service`  | BELOW_NORMAL     | API, líderes, vigilantes, registro de consumo (T127)          |
| `batch`    | IDLE             | mantenimiento (auditoría, compactación, poda), gate, copias, LLM |

La clase de CPU no lo es todo: lo que nace de una tarea programada hereda además memoria 2 y E/S
baja. Los recolectores suben también esas dos al arrancar, porque es la memoria lo que ha dañado a
la captura, y los demás se quedan como están (`priority_memory.py`, T141).

Dentro de un servicio, un hilo dedicado a trabajo de fondo baja al nivel `batch` con
`lower_thread` (T128: los ganchos del bróker en la API): THREAD_PRIORITY_LOWEST en un proceso
BELOW_NORMAL queda en 4, a la par de los trabajos IDLE y por debajo del resto del servicio.

Windows no deja morir de hambre a IDLE: un hilo que lleva unos segundos sin turno recibe un
impulso, así que lo pesado avanza aunque el equipo esté ocupado, solo que sin estorbar.

Solo actúa con `EIM_PRIORITY=on` (lo fija `scripts/servicio_continuo.ps1` y lo heredan los
hijos): las pruebas y las CLI a mano no cambian de prioridad. Windows hace heredar a los hijos
BELOW_NORMAL e IDLE, pero no ABOVE_NORMAL: por eso cada servicio fija la suya al arrancar
(`apply_role`) en vez de confiar en quién lo lanzó.

Un trabajo pesado lanzado a mano, por debajo de los servicios:

    python -m eim.operation.priority run batch -- python -m pytest -q
"""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from eim.operation import priority_memory, proc_access

ENV = "EIM_PRIORITY"
WINDOWS_CLASS = {"realtime": 0x8000, "service": 0x4000, "batch": 0x40}
POSIX_NICE = {"service": 5, "batch": 19}   # sin privilegios solo se puede bajar
ROLES = {
    "collector": "realtime", "hft_collector": "realtime", "liq_collector": "realtime",
    "api": "service", "leaders": "service", "watchdog": "service",
    "micro_watchdog": "service", "hft_watchdog": "service", "usage": "service",
}
INHERITED = ("service", "batch")           # niveles que Windows pasa a los hijos
THREAD_LOWEST = -2                          # THREAD_PRIORITY_LOWEST


def enabled(env: Mapping[str, str] | None = None) -> bool:
    v = (os.environ if env is None else env).get(ENV, "")
    return v.strip().lower() in ("on", "1", "true", "yes")


def _kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True)   # type: ignore[attr-defined]


def current_class() -> int | None:
    """Clase de prioridad de este proceso (Windows); None en otros sistemas o si falla."""
    if sys.platform != "win32":
        return None
    k = _kernel32()
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.GetPriorityClass.argtypes = [ctypes.c_void_p]
    return int(k.GetPriorityClass(k.GetCurrentProcess())) or None


def _set_class(cls: int) -> bool:
    k = _kernel32()
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    return bool(k.SetPriorityClass(k.GetCurrentProcess(), cls))


def tier_of(cls: int | None) -> str | None:
    return next((t for t, c in WINDOWS_CLASS.items() if c == cls), None)


def set_tier(tier: str) -> bool:
    """Fija el nivel de este proceso sin mirar `EIM_PRIORITY`. False si el sistema no lo admite
    (p. ej. subir la prioridad fuera de Windows) o si falla; nunca lanza."""
    if tier not in WINDOWS_CLASS:
        raise ValueError(f"nivel desconocido: {tier}")
    try:
        if sys.platform == "win32":
            return _set_class(WINDOWS_CLASS[tier])
        if tier in POSIX_NICE:
            os.setpriority(os.PRIO_PROCESS, 0, max(os.getpriority(os.PRIO_PROCESS, 0),
                                                   POSIX_NICE[tier]))
            return True
    except OSError:
        pass
    return False


def apply_role(role: str, env: Mapping[str, str] | None = None) -> str | None:
    """Al arrancar un servicio, si `EIM_PRIORITY` está activo: fija el nivel de su papel y deja
    que su usuario lo vea y lo pare desde cualquier sesión (`proc_access`, T127). Devuelve el
    nivel aplicado, o None si no se tocó el nivel."""
    if not enabled(env):
        return None
    proc_access.open_to_user()
    tier = ROLES.get(role)
    if tier == "realtime":
        priority_memory.raise_normal()     # T141: también la memoria y la E/S
    return tier if tier is not None and set_tier(tier) else None


@contextmanager
def lowered(tier: str = "batch", env: Mapping[str, str] | None = None) -> Iterator[None]:
    """Baja la prioridad de todo el proceso durante el bloque y luego la restaura: para el
    mantenimiento que un vigilante hace entre comprobación y comprobación (sus hilos de DuckDB
    y Parquet también bajan). Solo Windows y con `EIM_PRIORITY` activo; si no, no hace nada."""
    prev = current_class() if enabled(env) else None
    changed = prev is not None and prev != WINDOWS_CLASS[tier] and set_tier(tier)
    try:
        yield
    finally:
        if changed:
            _set_class(prev)


def thread_priority() -> int | None:
    """Prioridad relativa del hilo actual (Windows); None en otros sistemas."""
    if sys.platform != "win32":
        return None
    k = _kernel32()
    k.GetCurrentThread.restype = ctypes.c_void_p
    k.GetThreadPriority.argtypes = [ctypes.c_void_p]
    return int(k.GetThreadPriority(k.GetCurrentThread()))


def lower_thread(env: Mapping[str, str] | None = None) -> bool:
    """Baja el hilo actual al nivel `batch` para siempre: solo para hilos dedicados a trabajo de
    fondo. Solo Windows y con `EIM_PRIORITY` activo; nunca lanza."""
    if not enabled(env) or sys.platform != "win32":
        return False
    try:
        k = _kernel32()
        k.GetCurrentThread.restype = ctypes.c_void_p
        k.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
        return bool(k.SetThreadPriority(k.GetCurrentThread(), THREAD_LOWEST))
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eim.operation.priority", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="ejecuta una orden con prioridad baja (la heredan sus hijos)")
    r.add_argument("tier", choices=INHERITED)
    r.add_argument("command", nargs=argparse.REMAINDER, help="-- orden y argumentos")
    sub.add_parser("show", help="nivel de este proceso")
    a = ap.parse_args(argv)
    if a.cmd == "show":
        print(tier_of(current_class()) or "desconocido")
        return 0
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd:
        ap.error("falta la orden: run batch -- <orden> [args]")
    if not set_tier(a.tier):
        print(f"aviso: no se pudo fijar el nivel {a.tier}; se ejecuta igual", file=sys.stderr)
    return subprocess.call(cmd)  # noqa: S603 - orden explícita de quien llama


if __name__ == "__main__":
    raise SystemExit(main())
