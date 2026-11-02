"""T127: el usuario ve y para los servicios del EIM desde cualquier sesión. Se emula un servicio
de la sesión 0 (lista de permisos sin el usuario) y se comprueba que, al arrancar como servicio,
se abre al usuario solo con lo necesario; y que `detener_servicio.ps1` para primero los
vigilantes y nada más que lo pedido."""

import ctypes
import os
import shutil
import subprocess
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="permisos de procesos de Windows")

V2 = Path(__file__).resolve().parents[2]
STOP = V2 / "scripts" / "detener_servicio.ps1"
QUERY, TERMINATE, SUSPEND, VM_READ = 0x1000, 0x0001, 0x0800, 0x0010
VM_WRITE, CREATE_THREAD = 0x0020, 0x0002

# Un «servicio de la sesión 0»: solo SYSTEM en su lista de permisos, como los de la tarea S4U.
CHILD = r'''
import ctypes, os, sys
from ctypes import wintypes
a = ctypes.WinDLL("advapi32", use_last_error=True)
k = ctypes.WinDLL("kernel32")
k.GetCurrentProcess.restype = wintypes.HANDLE
a.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
a.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
                                        ctypes.POINTER(ctypes.c_void_p),
                                        ctypes.POINTER(wintypes.BOOL)]
a.SetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
sd, dacl, p, d = ctypes.c_void_p(), ctypes.c_void_p(), wintypes.BOOL(), wintypes.BOOL()
assert a.ConvertStringSecurityDescriptorToSecurityDescriptorW("D:(A;;0x1fffff;;;SY)", 1,
                                                              ctypes.byref(sd), None)
assert a.GetSecurityDescriptorDacl(sd, ctypes.byref(p), ctypes.byref(dacl), ctypes.byref(d))
assert a.SetSecurityInfo(k.GetCurrentProcess(), 6, 4, None, None, dacl, None) == 0
print(os.getpid(), flush=True)
sys.stdin.readline()
from eim.operation import priority
print(priority.apply_role("api") or "sin nivel", flush=True)
sys.stdin.readline()
'''


def can(pid: int, access: int) -> bool:
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    h = k.OpenProcess(access, False, pid)
    if h:
        k.CloseHandle(h)
    return bool(h)


def cmdline(pid: int) -> str:
    """Lo que ven el lanzador y el icono (WMI, como `servicio_continuo.ps1`)."""
    query = f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"
    return subprocess.run(["powershell", "-NoProfile", "-Command", query],
                          capture_output=True, text=True, timeout=60).stdout.strip()


def service(env_on: bool) -> tuple[subprocess.Popen, int]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("EIM_")}
    if env_on:
        env["EIM_PRIORITY"] = "on"
    proc = subprocess.Popen([sys.executable, "-c", CHILD], cwd=V2, env=env, text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    return proc, int(proc.stdout.readline())


def test_a_session0_like_service_opens_itself_to_its_user_and_no_more():
    proc, pid = service(env_on=True)
    try:
        assert not can(pid, QUERY) and not can(pid, TERMINATE)     # como desde la sesión 1
        assert cmdline(pid) == ""                                   # el lanzador no lo ve
        proc.stdin.write("\n")
        proc.stdin.flush()
        assert proc.stdout.readline().strip() == "service"
        assert all(can(pid, x) for x in (QUERY, TERMINATE, SUSPEND, VM_READ))
        assert "import ctypes" in cmdline(pid)                      # ahora sí
        # ni escribir en su memoria ni crear hilos (cambiar permisos sí puede: aquí el usuario es
        # el dueño del proceso, y al dueño Windows siempre se lo deja)
        assert not can(pid, VM_WRITE) and not can(pid, CREATE_THREAD)
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        h = k.OpenProcess(TERMINATE, False, pid)
        assert k.TerminateProcess(h, 9)                              # y se puede parar
        k.CloseHandle(h)
        assert proc.wait(15) is not None
    finally:
        proc.kill()


def test_outside_the_service_launcher_nothing_changes():
    proc, pid = service(env_on=False)
    try:
        proc.stdin.write("\n")
        proc.stdin.flush()
        assert proc.stdout.readline().strip() == "sin nivel"
        assert not can(pid, QUERY)
    finally:
        proc.kill()


@pytest.mark.skipif(not shutil.which("powershell"), reason="PowerShell")
def test_the_stop_script_stops_watchdogs_first_and_only_what_was_asked(tmp_path):
    mark = f"EIM_PRUEBA_{uuid.uuid4().hex}"

    def fake(*args: str) -> subprocess.Popen:
        return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", mark,
                                 *args], stdout=subprocess.DEVNULL)

    wd = fake("-m", "eim.operation", "run", "--execution", "paper")
    api = fake("-m", "uvicorn", "eim.api.main:app", "--port", "1")
    hft = fake("-m", "eim.data.collectors.hft_ws", "BTCUSDT", "--root", "x")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                              str(STOP), "-SoloCon", mark], capture_output=True, text=True,
                             timeout=120)
        assert out.returncode == 0, out.stdout + out.stderr
        lines = out.stdout.splitlines()
        vig = next(i for i, x in enumerate(lines) if x.startswith("Vigilantes:"))
        srv = next(i for i, x in enumerate(lines) if x.startswith("Servicios:"))
        assert vig < srv and str(wd.pid) in lines[vig] and str(api.pid) in lines[srv]
        assert wd.wait(15) is not None and api.wait(15) is not None
        assert hft.poll() is None                                   # la captura sigue
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                              str(STOP), "-SoloCon", mark, "-Todo"], capture_output=True,
                             text=True, timeout=120)
        assert out.returncode == 0 and hft.wait(15) is not None
    finally:
        for p in (wd, api, hft):
            p.kill()
