"""Consumo de CPU y memoria en Windows sin abrir los procesos (T127, registro de consumo).

`NtQuerySystemInformation(SystemProcessInformation)` devuelve en una sola llamada, sin permisos
especiales, todos los procesos con su padre, sesión, prioridad base, tiempo de CPU y memoria.
Por eso también se miden los servicios de la sesión 0 (tarea al encender), que desde la sesión
del usuario no se pueden abrir: ni `Get-Process` ni `psutil` leerían su CPU. Solo `ctypes`.
"""

from __future__ import annotations

import ctypes
import socket
import sys
from ctypes import wintypes
from typing import NamedTuple

FILETIME_UNIX_S = 11_644_473_600          # segundos entre 1601 y 1970
_PROCESS_INFO = 5                         # SystemProcessInformation
_LENGTH_MISMATCH = 0xC0000004
_INSUFFICIENT_BUFFER = 122
_MB = 1 << 20


class Proc(NamedTuple):
    pid: int
    ppid: int
    name: str
    session: int
    prio: int       # prioridad base: 4 IDLE, 6 BELOW_NORMAL, 8 NORMAL, 10 ABOVE_NORMAL, 13 HIGH
    created: int    # FILETIME (100 ns desde 1601): con el PID identifica al proceso
    cpu: int        # tiempo de CPU acumulado (usuario + núcleo), en 100 ns
    ram: int        # conjunto de trabajo privado (bytes): la RAM física que solo él ocupa
    commit: int     # memoria confirmada privada (bytes)

    @property
    def created_s(self) -> float:
        return self.created / 1e7 - FILETIME_UNIX_S


class _UnicodeString(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ushort), ("MaximumLength", ctypes.c_ushort),
                ("Buffer", ctypes.c_void_p)]


class _ProcessInfo(ctypes.Structure):   # SYSTEM_PROCESS_INFORMATION, hasta PrivatePageCount
    _fields_ = [
        ("NextEntryOffset", ctypes.c_ulong), ("NumberOfThreads", ctypes.c_ulong),
        ("WorkingSetPrivateSize", ctypes.c_longlong), ("HardFaultCount", ctypes.c_ulong),
        ("NumberOfThreadsHighWatermark", ctypes.c_ulong), ("CycleTime", ctypes.c_ulonglong),
        ("CreateTime", ctypes.c_longlong), ("UserTime", ctypes.c_longlong),
        ("KernelTime", ctypes.c_longlong), ("ImageName", _UnicodeString),
        ("BasePriority", ctypes.c_long), ("UniqueProcessId", ctypes.c_void_p),
        ("InheritedFromUniqueProcessId", ctypes.c_void_p), ("HandleCount", ctypes.c_ulong),
        ("SessionId", ctypes.c_ulong), ("UniqueProcessKey", ctypes.c_void_p),
        ("PeakVirtualSize", ctypes.c_size_t), ("VirtualSize", ctypes.c_size_t),
        ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t), ("PrivatePageCount", ctypes.c_size_t),
    ]


class _MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class _Tcp4Row(ctypes.Structure):       # MIB_TCPROW_OWNER_PID
    _fields_ = [("state", wintypes.DWORD), ("local_addr", wintypes.DWORD),
                ("local_port", wintypes.DWORD), ("remote_addr", wintypes.DWORD),
                ("remote_port", wintypes.DWORD), ("pid", wintypes.DWORD)]


class _Tcp6Row(ctypes.Structure):       # MIB_TCP6ROW_OWNER_PID
    _fields_ = [("local_addr", ctypes.c_ubyte * 16), ("local_scope", wintypes.DWORD),
                ("local_port", wintypes.DWORD), ("remote_addr", ctypes.c_ubyte * 16),
                ("remote_scope", wintypes.DWORD), ("remote_port", wintypes.DWORD),
                ("state", wintypes.DWORD), ("pid", wintypes.DWORD)]


def supported() -> bool:
    return sys.platform == "win32"


def _kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True)   # type: ignore[attr-defined]


_size = 1 << 20                           # último tamaño que bastó: no se tantea cada vez


def snapshot() -> dict[int, Proc]:
    """Todos los procesos del equipo, por PID."""
    global _size
    fn = ctypes.WinDLL("ntdll").NtQuerySystemInformation   # type: ignore[attr-defined]
    fn.restype = ctypes.c_ulong
    fn.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                   ctypes.POINTER(ctypes.c_ulong)]
    for _ in range(8):
        buf, need = ctypes.create_string_buffer(_size), ctypes.c_ulong(0)
        status = fn(_PROCESS_INFO, buf, _size, ctypes.byref(need))
        if status == 0:
            break
        if status != _LENGTH_MISMATCH:
            raise OSError(f"NtQuerySystemInformation: 0x{status:08X}")
        _size = max(_size * 2, need.value + (64 << 10))
    else:
        raise OSError("NtQuerySystemInformation: la lista de procesos no cabe")
    out, base, off = {}, ctypes.addressof(buf), 0
    while True:
        p = _ProcessInfo.from_address(base + off)
        pid = p.UniqueProcessId or 0
        img = p.ImageName
        name = ctypes.wstring_at(img.Buffer, img.Length // 2) if img.Buffer else (
            "System Idle Process" if pid == 0 else "")
        out[pid] = Proc(pid, p.InheritedFromUniqueProcessId or 0, name, p.SessionId,
                        p.BasePriority, p.CreateTime, p.UserTime + p.KernelTime,
                        p.WorkingSetPrivateSize, p.PagefileUsage)
        if not p.NextEntryOffset:
            return out
        off += p.NextEntryOffset


def system_times() -> tuple[int, int]:
    """(ocupado, total) en 100 ns sumados sobre todos los núcleos, desde el arranque."""
    idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if not _kernel32().GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
        raise ctypes.WinError(ctypes.get_last_error())   # type: ignore[attr-defined]

    def ft(t: wintypes.FILETIME) -> int:
        return (t.dwHighDateTime << 32) | t.dwLowDateTime

    total = ft(kern) + ft(user)           # el tiempo de núcleo ya incluye el ocioso
    return total - ft(idle), total


def memory() -> dict[str, int]:
    m = _MemoryStatus()
    m.dwLength = ctypes.sizeof(m)
    if not _kernel32().GlobalMemoryStatusEx(ctypes.byref(m)):
        raise ctypes.WinError(ctypes.get_last_error())   # type: ignore[attr-defined]
    return {"ram_load": int(m.dwMemoryLoad), "ram_free_mb": m.ullAvailPhys // _MB,
            "ram_total_mb": m.ullTotalPhys // _MB,
            "commit_mb": (m.ullTotalPageFile - m.ullAvailPageFile) // _MB,
            "commit_limit_mb": m.ullTotalPageFile // _MB}


def listeners(ports: set[int] | frozenset[int]) -> dict[int, int]:
    """Puerto TCP en escucha → PID de su dueño (IPv4 e IPv6), solo de `ports`."""
    out: dict[int, int] = {}
    get = ctypes.WinDLL("iphlpapi").GetExtendedTcpTable    # type: ignore[attr-defined]
    for family, row in ((socket.AF_INET, _Tcp4Row), (socket.AF_INET6, _Tcp6Row)):
        size = wintypes.DWORD(0)
        get(None, ctypes.byref(size), False, int(family), 3, 0)   # 3: solo en escucha
        for _ in range(4):
            buf = ctypes.create_string_buffer(size.value + 1024)
            size = wintypes.DWORD(len(buf))
            res = get(buf, ctypes.byref(size), False, int(family), 3, 0)
            if res != _INSUFFICIENT_BUFFER:
                break
        if res != 0:
            continue
        n = wintypes.DWORD.from_buffer(buf).value
        for r in (row * n).from_buffer(buf, ctypes.sizeof(wintypes.DWORD)):
            port = socket.ntohs(r.local_port & 0xFFFF)
            if port in ports:
                out.setdefault(port, int(r.pid))
    return out
