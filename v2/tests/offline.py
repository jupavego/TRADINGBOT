"""Suite sin red (T116): solo el bucle local; el resto falla al instante, como sin conexión.

Las pruebas usan fixtures (`tests/fixtures/`) o transportes falsos, pero el ciclo de operación
real sincroniza por su cuenta liquidaciones (`data.binance.vision`) y titulares RSS: con conexión
eso eran ~20 s de descargas por prueba y un resultado que dependía de la red del equipo. Aquí
toda resolución o conexión a un host que no sea el bucle local se rechaza dentro del proceso de
pytest, igual que en un equipo desconectado; el código ya trata ese caso («red caída»).
"""

from __future__ import annotations

import errno
import ipaddress
import socket

_real_getaddrinfo = socket.getaddrinfo
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def is_local(host: object) -> bool:
    """True si `host` es el bucle local (o «cualquiera», para escuchar)."""
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    h = str(host).strip("[]").split("%")[0].lower()
    if h in ("", "localhost") or h.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


def _host(address: object) -> object:
    """Host de una dirección AF_INET/AF_INET6; None para AF_UNIX (una ruta: no sale del equipo)."""
    return address[0] if isinstance(address, tuple) and address else None


def _getaddrinfo(host, *args, **kwargs):
    if not is_local(host):
        raise socket.gaierror(socket.EAI_NONAME, f"suite sin red: {host}")
    return _real_getaddrinfo(host, *args, **kwargs)


def _connect(self, address):
    if not is_local(_host(address)):
        raise ConnectionRefusedError(errno.ECONNREFUSED, f"suite sin red: {_host(address)}")
    return _real_connect(self, address)


def _connect_ex(self, address):
    if not is_local(_host(address)):
        return errno.ECONNREFUSED
    return _real_connect_ex(self, address)


def block_network() -> None:
    socket.getaddrinfo = _getaddrinfo
    socket.socket.connect = _connect
    socket.socket.connect_ex = _connect_ex
