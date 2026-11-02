"""Proceso de un trabajo pesado (T127): arrancar con su nivel, pausar, reanudar y matar el árbol.

En Windows el trabajo va dentro de un «Job Object» propio. Así se pausa y se reanuda con todos
sus hijos (`NtSuspendProcess` sobre cada proceso del objeto) y, si el ejecutor muere, Windows
cierra el objeto y mata el trabajo (`KILL_ON_JOB_CLOSE`): ningún trabajo queda suspendido para
siempre ni huérfano. Arranca suspendido, entra en el objeto y solo entonces echa a andar, así
que ni un nieto se escapa. Fuera de Windows: grupo de procesos propio y SIGSTOP/SIGCONT.
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

WIN = sys.platform == "win32"
_CLASS = {"batch": 0x40, "service": 0x4000}          # IDLE, BELOW_NORMAL (los heredan los hijos)
_NICE = {"batch": 19, "service": 5}
_SUSPENDED, _NO_WINDOW = 0x4, 0x08000000
_KILL_ON_CLOSE = 0x2000
_EXTENDED_LIMITS, _PID_LIST = 9, 3
_SUSPEND_RESUME = 0x0800


class _BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", ctypes.c_ulonglong * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _PidList(ctypes.Structure):     # JOBOBJECT_BASIC_PROCESS_ID_LIST
    _fields_ = [("assigned", wintypes.DWORD), ("listed", wintypes.DWORD),
                ("ids", ctypes.c_size_t * 1024)]


def _k32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)      # type: ignore[attr-defined]
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                          wintypes.DWORD]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                            wintypes.DWORD, ctypes.c_void_p]
    k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return k


def _nt(fn: str, handle) -> None:
    f = getattr(ctypes.WinDLL("ntdll"), fn)                  # type: ignore[attr-defined]
    f.restype = ctypes.c_ulong
    f.argtypes = [wintypes.HANDLE]
    if (st := f(handle)) != 0:
        raise OSError(f"{fn}: 0x{st:08X}")


def _check(ok) -> None:
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())      # type: ignore[attr-defined]


class JobProcess:
    """Un trabajo en marcha. `suspend`/`resume` actúan sobre todo su árbol."""

    def __init__(self, cmd: list[str], cwd: Path, out: Path, tier: str = "batch",
                 env: dict[str, str] | None = None) -> None:
        if tier not in _CLASS:
            raise ValueError(f"nivel desconocido: {tier}")
        self.suspended = False
        self._log = out.open("ab")
        self._job = None
        try:
            if WIN:
                self._start_windows(cmd, cwd, tier, env)
            else:
                self.proc = subprocess.Popen(  # noqa: S603 - orden explícita de quien encola
                    cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=self._log,
                    stderr=subprocess.STDOUT, start_new_session=True,
                    preexec_fn=lambda: os.nice(_NICE[tier]))  # noqa: PLW1509
        except BaseException:
            self._log.close()
            raise
        self.pid = self.proc.pid

    def _start_windows(self, cmd, cwd, tier, env) -> None:
        k = _k32()
        self._job = k.CreateJobObjectW(None, None)
        _check(self._job)
        lim = _ExtendedLimits()
        lim.BasicLimitInformation.LimitFlags = _KILL_ON_CLOSE
        _check(k.SetInformationJobObject(self._job, _EXTENDED_LIMITS, ctypes.byref(lim),
                                         ctypes.sizeof(lim)))
        self.proc = subprocess.Popen(  # noqa: S603 - orden explícita de quien encola
            cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=self._log,
            stderr=subprocess.STDOUT, creationflags=_SUSPENDED | _NO_WINDOW | _CLASS[tier])
        try:
            _check(k.AssignProcessToJobObject(self._job, int(self.proc._handle)))  # type: ignore[attr-defined]
            _nt("NtResumeProcess", int(self.proc._handle))  # type: ignore[attr-defined]
        except BaseException:
            self.proc.kill()
            raise

    def pids(self) -> list[int]:
        if not WIN:
            return [self.pid]
        lst = _PidList()
        if not _k32().QueryInformationJobObject(self._job, _PID_LIST, ctypes.byref(lst),
                                                ctypes.sizeof(lst), None):
            return [self.pid]
        return [int(p) for p in lst.ids[:lst.listed]]

    def _each(self, fn: str) -> None:
        k = _k32()
        for pid in self.pids():
            h = k.OpenProcess(_SUSPEND_RESUME, False, pid)
            if not h:
                continue                                     # acaba de terminar
            try:
                _nt(fn, h)
            except OSError:
                pass
            finally:
                k.CloseHandle(h)

    def suspend(self) -> None:
        if self.suspended:
            return
        if WIN:
            self._each("NtSuspendProcess")
        else:
            os.killpg(self.pid, signal.SIGSTOP)
        self.suspended = True

    def resume(self) -> None:
        if not self.suspended:
            return
        if WIN:
            self._each("NtResumeProcess")
        else:
            os.killpg(self.pid, signal.SIGCONT)
        self.suspended = False

    def poll(self) -> int | None:
        return self.proc.poll()

    def kill(self) -> None:
        if WIN and self._job:
            _k32().TerminateJobObject(self._job, 1)
        elif not WIN:
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.proc.wait(30)

    def close(self) -> None:
        """Cierra el objeto: si aún queda algún proceso del trabajo, Windows lo mata."""
        if WIN and self._job:
            _k32().CloseHandle(self._job)
            self._job = None
        self._log.close()
