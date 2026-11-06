"""Reproduce la pérdida del socket de escucha (T140): `python -m eim.operation.accept_check`.

Corre uvicorn real en un puerto efímero de loopback, sin tocar los servicios:
1. `GET /block` bloquea el bucle, como una vista pesada o un equipo saturado.
2. Durante el bloqueo, una conexión consume el `accept` pendiente y otra queda en la cola.
3. Esa segunda conexión se rinde, de la manera que indique el cliente.
4. Al soltar el bucle se mira si el puerto sigue en escucha y si responde HTTP.

La tabla que imprime compara los dos bucles y varias formas de rendirse. Solo tiene sentido en
Windows: el fallo es de `ProactorEventLoop`.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

import uvicorn

from eim.operation.event_loop import LOOP_SPEC
from eim.operation.port_watch import listening

LOOPS = {"proactor": "asyncio", "selector": LOOP_SPEC}   # en Windows, «asyncio» es Proactor
HOST = "127.0.0.1"


def _connect(port: int) -> socket.socket:
    return socket.create_connection((HOST, port), timeout=5)


def _get(port: int, path: str, timeout: float = 5.0) -> str:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}{path}", timeout=timeout) as r:  # noqa: S310
            return str(r.status)
    except Exception as exc:  # noqa: BLE001 - el resultado es el nombre del fallo
        return type(exc).__name__


def _rst(port: int) -> None:
    """Corta con RST: el `accept` que recoja esta conexión falla con `WinError 64`."""
    c = _connect(port)
    linger = struct.pack("hh" if sys.platform == "win32" else "ii", 1, 0)
    c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
    c.close()


def _fin(port: int) -> None:
    _connect(port).close()


def _python(port: int) -> None:
    _get(port, "/ping", timeout=1.0)


def _powershell(port: int) -> None:
    """Como `scripts/icono_bandeja.ps1`, con menos espera."""
    subprocess.run(  # noqa: S603
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",  # noqa: S607
         f"try {{ Invoke-RestMethod 'http://{HOST}:{port}/v2/health' -TimeoutSec 1 }} catch {{ }}"],
        capture_output=True, timeout=60, check=False)


CLIENTS: dict[str, Callable[[int], None]] = {"rst": _rst, "fin": _fin, "python": _python,
                                             "powershell": _powershell}


@dataclass
class Result:
    loop: str
    client: str
    loop_class: str = ""
    listening: bool | None = None
    http: str = ""
    messages: list[str] = field(default_factory=list)


class _App:
    """Aplicación ASGI mínima: `/block` retiene el bucle hasta que se le suelte."""

    def __init__(self, result: Result) -> None:
        self.result = result
        self.entered, self.release = threading.Event(), threading.Event()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            self.result.loop_class = type(asyncio.get_running_loop()).__name__
            while True:
                kind = (await receive())["type"].rpartition(".")[2]
                await send({"type": f"lifespan.{kind}.complete"})
                if kind == "shutdown":
                    return
        if scope["path"] == "/block":
            self.entered.set()
            self.release.wait(timeout=30)    # bloquea el bucle a propósito
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-length", b"2")]})
        await send({"type": "http.response.body", "body": b"ok"})


class _Capture(logging.Handler):
    def __init__(self, into: list[str]) -> None:
        super().__init__()
        self.into = into

    def emit(self, record: logging.LogRecord) -> None:
        self.into.append(record.getMessage().splitlines()[0])


def _free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _drive(app: _App, port: int, give_up: Callable[[int], None], server: uvicorn.Server) -> None:
    try:
        for _ in range(400):
            if server.started:
                break
            time.sleep(0.05)
        blocker = threading.Thread(target=_get, args=(port, "/block", 35.0))
        blocker.start()
        app.entered.wait(timeout=20)
        first = _connect(port)               # consume el `accept` pendiente
        give_up(port)                        # esta queda en la cola del sistema y se rinde
        time.sleep(0.2)
        app.release.set()
        blocker.join(timeout=40)
        time.sleep(0.5)                      # el bucle procesa lo que tenía en cola
        first.close()
        app.result.listening = listening(port)
        app.result.http = _get(port, "/ping")
    finally:
        app.release.set()
        server.should_exit = True


def run_case(loop: str, client: str) -> Result:
    """Un caso completo. Devuelve qué bucle corrió de verdad y si el puerto sobrevivió."""
    result = Result(loop, client)
    app, port = _App(result), _free_port()
    capture = _Capture(result.messages)
    logger = logging.getLogger("asyncio")
    logger.addHandler(capture)
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, loop=LOOPS[loop],
                                           lifespan="on", log_level="critical"))
    threading.Thread(target=_drive, args=(app, port, CLIENTS[client], server),
                     daemon=True).start()
    try:
        server.run()
    finally:
        logger.removeHandler(capture)
    return result


def main() -> int:
    print(f"Python {sys.version.split()[0]} · uvicorn {uvicorn.__version__} · {sys.platform}\n")
    print("| Bucle | Cliente que se rinde | Puerto después | HTTP | `Accept failed` |")
    print("|---|---|---|---|---|")
    for loop in LOOPS:
        for client in CLIENTS:
            r = run_case(loop, client)
            failed = "sí" if any("Accept failed" in m for m in r.messages) else "no"
            state = {True: "abierto", False: "**cerrado**", None: "desconocido"}[r.listening]
            print(f"| {r.loop_class} | {client} | {state} | {r.http} | {failed} |", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
