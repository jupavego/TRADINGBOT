"""T140: el bucle adoptado conserva el puerto cuando un cliente corta durante un bloqueo.

Uvicorn real sobre loopback (`eim/operation/accept_check.py`). La prueba de control fija que el
arnés sigue reproduciendo el fallo: sin ella, «Selector sobrevive» podría ser cierto solo porque el
arnés dejó de provocarlo.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
import uvicorn

import eim
from eim.operation.__main__ import api_cmd
from eim.operation.accept_check import run_case
from eim.operation.event_loop import LOOP_SPEC, selector_loop

windows = pytest.mark.skipif(sys.platform != "win32", reason="el fallo es de ProactorEventLoop")
ONLY_ON_PROACTOR = ("create_subprocess_exec", "create_subprocess_shell", "subprocess_exec",
                    "subprocess_shell", "connect_read_pipe", "connect_write_pipe",
                    "anyio.run_process", "anyio.open_process")


@windows
def test_control_the_harness_still_loses_the_port_on_proactor():
    """Si esto falla, otra versión de Python o de uvicorn lo ha cambiado: hay que revisar si
    `LOOP_SPEC` sigue haciendo falta y si esta reproducción sigue valiendo."""
    r = run_case("proactor", "rst")
    assert r.loop_class == "ProactorEventLoop"
    assert r.listening is False and r.http != "200"
    assert any("Accept failed" in m for m in r.messages)


@windows
def test_the_adopted_loop_keeps_the_port_and_keeps_answering():
    r = run_case("selector", "rst")
    assert "Selector" in r.loop_class
    assert r.listening is True and r.http == "200"
    assert not any("Accept failed" in m for m in r.messages)


def test_the_api_is_launched_with_the_adopted_loop():
    cmd = api_cmd(8123)
    assert cmd[cmd.index("--loop") + 1] == LOOP_SPEC and cmd[cmd.index("--port") + 1] == "8123"
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1"          # API solo local


def test_uvicorn_resolves_the_loop_as_a_selector():
    factory = uvicorn.Config("x:y", loop=LOOP_SPEC).get_loop_factory()
    assert factory is selector_loop
    loop = factory()
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
    finally:
        loop.close()


def test_nothing_in_eim_needs_what_the_selector_loop_lacks():
    """`SelectorEventLoop` no admite subprocesos ni tuberías de asyncio en Windows."""
    root = Path(eim.__file__).parent
    found = [f"{p.relative_to(root)}: {name}" for p in root.rglob("*.py")
             if p.name != "event_loop.py"
             for name in ONLY_ON_PROACTOR if name in p.read_text(encoding="utf-8")]
    assert found == []
