"""Prioridad de memoria y de E/S de los procesos (T141, decisión ◆B del usuario, 2026-11-06).

T126 ajustó la clase de CPU, pero los procesos que nacen de una tarea programada (prioridad 7)
heredan además memoria 2 y E/S baja, frente a 5 y normal de cualquier programa abierto, y Windows
quita primero las páginas de prioridad baja. Con la CPU llena la captura aguantó; con presión de
memoria bajó de 132 a 18–40 MB, su cola llegó a 5 662 mensajes y hubo 3 horas incompletas
(`PLAN/notas/T141_carga_ajena.md`). Por eso los recolectores en vivo suben a 5 y normal: al
arrancar (`priority.apply_role`) o, sin reiniciarlos, con `apply`. Ocupan unos 150 MB.

La API y el resto de los servicios se quedan como están. Subirlos es otra decisión (◆C), y hacerlo
antes que la captura la dejaría como la primera en perder memoria.

    python -m eim.operation.priority_memory show [--data-dir data]    # lo que tiene cada servicio
    python -m eim.operation.priority_memory apply [--data-dir data]   # sube a los recolectores
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path

MEMORY_NORMAL, IO_NORMAL = 5, 2
_MEMORY_INFO, _IO_INFO, _THREAD_IO_INFO = 0, 33, 22   # ProcessMemoryPriority, ProcessIoPriority…
_QUERY, _SET = 0x0400, 0x0200                         # PROCESS_QUERY_INFORMATION, _SET_INFORMATION
_THREAD_QUERY = 0x0040 | 0x0800                       # THREAD_QUERY_(LIMITED_)INFORMATION
_SNAP_THREADS = 4
_REAL_MIN_COMMIT = 4 << 20                            # por debajo, un lanzador del venv
_ABOVE_NORMAL = 10                                    # prioridad base de esa clase


class _Memory(ctypes.Structure):
    _fields_ = [("priority", wintypes.ULONG)]


class _ThreadEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", ctypes.c_long), ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", wintypes.DWORD)]


def _dlls():
    k = ctypes.WinDLL("kernel32", use_last_error=True)        # type: ignore[attr-defined]
    nt = ctypes.WinDLL("ntdll")                               # type: ignore[attr-defined]
    h, dword, void = wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p
    k.GetCurrentProcess.restype = h
    k.OpenProcess.restype = k.OpenThread.restype = k.CreateToolhelp32Snapshot.restype = h
    k.OpenProcess.argtypes = k.OpenThread.argtypes = [dword, wintypes.BOOL, dword]
    k.CloseHandle.argtypes = [h]
    k.GetProcessInformation.argtypes = k.SetProcessInformation.argtypes = [h, ctypes.c_int, void,
                                                                           dword]
    k.GetThreadInformation.argtypes = [h, ctypes.c_int, void, dword]
    k.Thread32First.argtypes = k.Thread32Next.argtypes = [h, void]
    nt.NtQueryInformationProcess.argtypes = [h, ctypes.c_ulong, void, ctypes.c_ulong, void]
    nt.NtQueryInformationThread.argtypes = [h, ctypes.c_int, void, ctypes.c_ulong, void]
    nt.NtSetInformationProcess.argtypes = [h, ctypes.c_ulong, void, ctypes.c_ulong]
    nt.NtSetInformationProcess.restype = nt.NtQueryInformationProcess.restype = ctypes.c_ulong
    nt.NtQueryInformationThread.restype = ctypes.c_ulong
    return k, nt


def set_levels(pid: int | None, memory: int, io: int) -> bool:
    """Fija las dos prioridades de un proceso y de sus hilos en marcha (`pid` None: este proceso).
    False si Windows no lo deja, o fuera de Windows; nunca lanza."""
    if sys.platform != "win32":
        return False
    try:
        k, nt = _dlls()
        h = k.GetCurrentProcess() if pid is None else k.OpenProcess(_SET, False, pid)
        if not h:
            return False
        try:
            mem, level = _Memory(memory), ctypes.c_ulong(io)
            ok = k.SetProcessInformation(h, _MEMORY_INFO, ctypes.byref(mem), ctypes.sizeof(mem))
            return bool(ok) and nt.NtSetInformationProcess(h, _IO_INFO, ctypes.byref(level), 4) == 0
        finally:
            if pid is not None:
                k.CloseHandle(h)
    except (OSError, AttributeError):
        return False


def raise_normal(pid: int | None = None) -> bool:
    return set_levels(pid, MEMORY_NORMAL, IO_NORMAL)


def _thread_levels(k, nt, pid: int) -> dict[str, int]:
    """Hilos de `pid` por sus valores, «memoria/E/S»: lo que de verdad usa Windows al paginar."""
    snap, out = k.CreateToolhelp32Snapshot(_SNAP_THREADS, 0), {}
    try:
        entry = _ThreadEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = k.Thread32First(snap, ctypes.byref(entry))
        while more:
            if entry.th32OwnerProcessID == pid:
                t = k.OpenThread(_THREAD_QUERY, False, entry.th32ThreadID)
                if t:
                    mem, io = _Memory(), ctypes.c_ulong(0)
                    k.GetThreadInformation(t, _MEMORY_INFO, ctypes.byref(mem), ctypes.sizeof(mem))
                    nt.NtQueryInformationThread(t, _THREAD_IO_INFO, ctypes.byref(io), 4, None)
                    k.CloseHandle(t)
                    key = f"{mem.priority}/{io.value}"
                    out[key] = out.get(key, 0) + 1
            more = k.Thread32Next(snap, ctypes.byref(entry))
    finally:
        k.CloseHandle(snap)
    return out


def read(pid: int) -> dict | None:
    """Memoria y E/S de un proceso y de sus hilos; None si no se puede abrir o fuera de Windows."""
    if sys.platform != "win32":
        return None
    k, nt = _dlls()
    h = k.OpenProcess(_QUERY, False, pid)
    if not h:
        return None
    try:
        mem, io = _Memory(), ctypes.c_ulong(0)
        if not k.GetProcessInformation(h, _MEMORY_INFO, ctypes.byref(mem), ctypes.sizeof(mem)):
            return None
        if nt.NtQueryInformationProcess(h, _IO_INFO, ctypes.byref(io), 4, None) != 0:
            return None
        return {"memory": int(mem.priority), "io": int(io.value),
                "threads": _thread_levels(k, nt, pid)}
    finally:
        k.CloseHandle(h)


def services(data_dir: Path) -> list[dict]:
    """Procesos reales de cada servicio del EIM, sin lanzadores del venv, ordenados por papel."""
    from eim.operation import usage_roles, usage_win

    procs = usage_win.snapshot()
    roles = usage_roles.attribute(
        procs, usage_roles.spool_roles(Path(data_dir) / "obs" / "spool", procs),
        usage_win.listeners(frozenset(usage_roles.PORT_ROLES)))
    return sorted(({"role": role, "pid": pid, "cpu_prio": procs[pid].prio,
                    "session": procs[pid].session}
                   for pid, role in roles.items() if procs[pid].commit >= _REAL_MIN_COMMIT),
                  key=lambda s: (s["role"], s["pid"]))


def targets(rows: list[dict]) -> list[dict]:
    """Los recolectores en vivo: lo que ◆B sube. La API no está, ni debe estarlo sin decidir ◆C.
    Solo los que ya tomaron su clase ABOVE_NORMAL: su lanzador, en BELOW_NORMAL, solo espera."""
    from eim.operation.priority import ROLES

    return [r for r in rows
            if ROLES.get(r["role"]) == "realtime" and r["cpu_prio"] >= _ABOVE_NORMAL]


def apply(rows: list[dict]) -> list[dict]:
    """Sube a los recolectores y comprueba leyendo de vuelta, hilo a hilo."""
    out = []
    for r in targets(rows):
        before = read(r["pid"])
        done = raise_normal(r["pid"])
        after = read(r["pid"])
        ok = done and after is not None and set(after["threads"]) == {
            f"{MEMORY_NORMAL}/{IO_NORMAL}"}
        out.append({**r, "before": before, "after": after, "ok": ok})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eim.operation.priority_memory", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("show", "apply"))
    ap.add_argument("--data-dir", default="data")
    a = ap.parse_args(argv)
    rows = services(Path(a.data_dir))
    if a.cmd == "show":
        for r in rows:
            print(json.dumps({**r, **(read(r["pid"]) or {"memory": None})}, ensure_ascii=False))
        return 0
    done = apply(rows)
    for r in done:
        print(json.dumps(r, ensure_ascii=False))
    if not done:
        print("No hay recolectores en vivo a los que subir.", file=sys.stderr)
    return 0 if done and all(r["ok"] for r in done) else 1


if __name__ == "__main__":
    raise SystemExit(main())
