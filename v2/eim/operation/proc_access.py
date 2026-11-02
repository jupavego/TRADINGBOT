"""Que el usuario pueda ver, pausar y parar los servicios del EIM desde cualquier sesión (T127,
entregable 5).

Los procesos que lanza la tarea al encender (S4U, sesión 0) nacen con una lista de permisos que
no incluye al usuario, aunque corren con su misma cuenta. Desde su sesión, Windows le niega
hasta consultarlos: ni el lanzador ve su línea de órdenes, ni «Parar servicio» del icono los
detiene; para eso hacía falta una consola de administrador. Cada servicio, al arrancar
(`priority.apply_role`, con `EIM_PRIORITY=on`), añade a su propia lista un permiso para el
usuario de su cuenta: consultar, leer su línea de órdenes, esperar, pausar y terminar. Este
permiso no incluye escribir en su memoria, crear hilos ni cambiar sus permisos.

Es lo mismo que ya tiene cualquier programa abierto en la sesión del usuario, así que no amplía
nada. Una tarea elevada que ejecuta un script editable por el usuario (la alternativa de
T127.md) sería, en cambio, una puerta para saltarse el UAC.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

GRANT = (0x0001         # PROCESS_TERMINATE
         | 0x0010       # PROCESS_VM_READ (línea de órdenes por WMI)
         | 0x0400       # PROCESS_QUERY_INFORMATION
         | 0x0800       # PROCESS_SUSPEND_RESUME
         | 0x1000       # PROCESS_QUERY_LIMITED_INFORMATION
         | 0x00020000   # READ_CONTROL
         | 0x00100000)  # SYNCHRONIZE
_KERNEL_OBJECT, _DACL, _TOKEN_QUERY, _TOKEN_USER = 6, 0x4, 0x8, 1
_GRANT_ACCESS, _TRUSTEE_IS_SID, _TRUSTEE_IS_USER = 1, 0, 1


class _Trustee(ctypes.Structure):
    _fields_ = [("pMultipleTrustee", ctypes.c_void_p), ("MultipleTrusteeOperation", ctypes.c_int),
                ("TrusteeForm", ctypes.c_int), ("TrusteeType", ctypes.c_int),
                ("ptstrName", ctypes.c_void_p)]


class _ExplicitAccess(ctypes.Structure):
    _fields_ = [("grfAccessPermissions", wintypes.DWORD), ("grfAccessMode", ctypes.c_int),
                ("grfInheritance", wintypes.DWORD), ("Trustee", _Trustee)]


def _dlls():
    k = ctypes.WinDLL("kernel32", use_last_error=True)       # type: ignore[attr-defined]
    a = ctypes.WinDLL("advapi32", use_last_error=True)       # type: ignore[attr-defined]
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.LocalFree.argtypes = [ctypes.c_void_p]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    a.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    a.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                      wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    a.GetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p,
                                  ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                                  ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    a.SetEntriesInAclW.argtypes = [wintypes.ULONG, ctypes.POINTER(_ExplicitAccess),
                                   ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    a.SetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p,
                                  ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    return k, a


def open_to_user() -> bool:
    """Concede `GRANT` sobre este proceso al usuario de su cuenta. False si no se pudo o fuera
    de Windows; nunca lanza (un servicio arranca igual)."""
    if sys.platform != "win32":
        return False
    try:
        k, a = _dlls()
        me, tok = k.GetCurrentProcess(), wintypes.HANDLE()
        if not a.OpenProcessToken(me, _TOKEN_QUERY, ctypes.byref(tok)):
            return False
        try:
            n = wintypes.DWORD()
            a.GetTokenInformation(tok, _TOKEN_USER, None, 0, ctypes.byref(n))
            buf = ctypes.create_string_buffer(n.value)
            if not a.GetTokenInformation(tok, _TOKEN_USER, buf, n, ctypes.byref(n)):
                return False
            sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]   # TOKEN_USER.User.Sid
            dacl, sd, new = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
            if a.GetSecurityInfo(me, _KERNEL_OBJECT, _DACL, None, None, ctypes.byref(dacl), None,
                                 ctypes.byref(sd)):
                return False
            try:
                ea = _ExplicitAccess(GRANT, _GRANT_ACCESS, 0,
                                     _Trustee(None, 0, _TRUSTEE_IS_SID, _TRUSTEE_IS_USER, sid))
                if a.SetEntriesInAclW(1, ctypes.byref(ea), dacl, ctypes.byref(new)):
                    return False
                return a.SetSecurityInfo(me, _KERNEL_OBJECT, _DACL, None, None, new, None) == 0
            finally:
                k.LocalFree(new)
                k.LocalFree(sd)
        finally:
            k.CloseHandle(tok)
    except (OSError, AttributeError):
        return False
