"""Bucle de eventos de la API (T140): `SelectorEventLoop` también en Windows.

En Windows uvicorn usa `ProactorEventLoop`, y ese bucle cierra el socket de escucha para siempre
cuando falla un `accept` (`asyncio/proactor_events.py`, «Accept failed on a socket»). Basta con que
el bucle esté ocupado y un cliente corte su conexión antes de que se acepte: el proceso sigue vivo y
sin puerto. Con `SelectorEventLoop` el socket sobrevive. La evidencia está en
`PLAN/notas/T140_api_sin_puerto.md` §6 y se repite con `python -m eim.operation.accept_check`.

Lo que se cede: `select` admite hasta 512 sockets en Windows (la API usa unas decenas) y este bucle
no admite `asyncio.create_subprocess_*` ni tuberías, que `eim/` no usa (lo fija una prueba).
"""

from __future__ import annotations

import asyncio

LOOP_SPEC = "eim.operation.event_loop:selector_loop"     # lo que recibe `uvicorn --loop`


def selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()
