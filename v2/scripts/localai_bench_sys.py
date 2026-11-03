"""Equipo y memoria para el banco de motores locales (T62), sin dependencias nuevas (ctypes).

La RAM que importa es la libre con los servicios de EIM en marcha, no la total: `system_info`
anota qué servicios corren y cuánto ocupan, y `Sampler` registra en segundo plano la RAM libre
mínima del sistema y el pico de memoria privada de los procesos que se miden.
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path

MB = 1024 * 1024
WIN = os.name == "nt"
SERVICES = ("eim.operation", "uvicorn eim.api", "eim.leaders", "eim.data.collectors",
            "ollama.exe", "llama-server")


class _MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64)]


class _ProcMem(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def ram_mb() -> dict:
    """RAM total y libre del sistema (MB)."""
    if not WIN:
        return {"total_mb": None, "avail_mb": None}
    st = _MemStatus()
    st.dwLength = ctypes.sizeof(_MemStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return {"total_mb": round(st.ullTotalPhys / MB), "avail_mb": round(st.ullAvailPhys / MB)}


def proc_mem_mb(pid: int) -> dict | None:
    """Conjunto de trabajo y memoria privada (actual y pico) de un proceso, en MB."""
    if not WIN:
        return None
    h = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
    if not h:
        return None
    try:
        pm = _ProcMem()
        pm.cb = ctypes.sizeof(_ProcMem)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pm), pm.cb):
            return None
        return {"ws_mb": round(pm.WorkingSetSize / MB),
                "peak_ws_mb": round(pm.PeakWorkingSetSize / MB),
                "private_mb": round(pm.PagefileUsage / MB),
                "peak_private_mb": round(pm.PeakPagefileUsage / MB)}
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def processes() -> list[dict]:
    """Procesos con su línea de órdenes (PowerShell/CIM; en Windows no hay psutil en el gate)."""
    if not WIN:
        return []
    ps = ("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,"
          "CommandLine,WorkingSetSize | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                             text=True, timeout=60, encoding="utf-8", errors="replace").stdout
        rows = json.loads(out or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return rows if isinstance(rows, list) else [rows]


def find_pids(name: str) -> list[int]:
    """PID de los procesos cuyo ejecutable se llama `name` (rápido: EnumProcesses + ctypes)."""
    if not WIN:
        return []
    arr = (wintypes.DWORD * 4096)()
    got = wintypes.DWORD()
    if not ctypes.windll.psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(got)):
        return []
    out, buf = [], ctypes.create_unicode_buffer(1024)
    for pid in arr[: got.value // ctypes.sizeof(wintypes.DWORD)]:
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            continue
        try:
            size = wintypes.DWORD(len(buf))
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                if Path(buf.value).name.lower() == name.lower():
                    out.append(int(pid))
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    return out


def services() -> dict:
    """Servicios de EIM y motores en marcha, con su memoria (conjunto de trabajo)."""
    found: dict[str, dict] = {}
    for p in processes():
        cmd = (p.get("CommandLine") or "") + " " + (p.get("Name") or "")
        for key in SERVICES:
            if key in cmd:
                d = found.setdefault(key, {"procs": 0, "ws_mb": 0})
                d["procs"] += 1
                d["ws_mb"] += round((p.get("WorkingSetSize") or 0) / MB)
                break
    return found


def _cpu_name() -> str:
    if WIN:
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                               r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    return platform.processor()


def gpus() -> list[dict]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    q = "name,memory.total,memory.used,driver_version,compute_cap"
    try:
        out = subprocess.run([exe, f"--query-gpu={q}", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.strip().splitlines():
        f = [x.strip() for x in line.split(",")]
        if len(f) == 5:
            rows.append({"name": f[0], "vram_mb": int(f[1]), "used_mb": int(f[2]),
                         "driver": f[3], "compute_cap": f[4]})
    return rows


def tool_version(exe: str | None, *args: str) -> str | None:
    if not exe or not Path(exe).exists() and not shutil.which(exe):
        return None
    try:
        out = subprocess.run([exe, *args], capture_output=True, text=True, timeout=30,
                             encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    first = (out.stdout or out.stderr).strip().splitlines()
    return first[0].split(" Copyright")[0][:120] if first else None


def system_info(machine: str) -> dict:
    return {"machine": machine, "cpu": _cpu_name(), "threads": os.cpu_count(),
            "os": platform.platform(), "python": platform.python_version(), **ram_mb(),
            "gpus": gpus(), "services": services(),
            "ffmpeg": tool_version(shutil.which("ffmpeg"), "-version"),
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


class Sampler:
    """Muestrea cada `every` s la RAM libre del sistema y la memoria de `pids` (o de los
    procesos que devuelva `pid_fn`, para motores que relanzan su proceso al cargar)."""

    def __init__(self, pids: list[int] | None = None, pid_fn=None, every: float = 0.5) -> None:
        self.pids, self.pid_fn, self.every = list(pids or []), pid_fn, every
        self.min_avail_mb: int | None = None
        self.peak_private_mb = 0
        self.peak_ws_mb = 0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            avail = ram_mb()["avail_mb"]
            if avail is not None:
                low = self.min_avail_mb
                self.min_avail_mb = avail if low is None else min(low, avail)
            pids = self.pid_fn() if self.pid_fn else self.pids
            priv = ws = 0
            for pid in pids:
                m = proc_mem_mb(pid)
                if m:
                    priv += m["private_mb"]
                    ws += m["ws_mb"]
            self.peak_private_mb = max(self.peak_private_mb, priv)
            self.peak_ws_mb = max(self.peak_ws_mb, ws)
            self._stop.wait(self.every)

    def __enter__(self) -> Sampler:
        self._t.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._t.join(timeout=5)

    def result(self) -> dict:
        return {"min_avail_mb": self.min_avail_mb, "peak_private_mb": self.peak_private_mb,
                "peak_ws_mb": self.peak_ws_mb}
