"""T116: la suite no hereda el equipo — entorno `EIM_*` fijo y sin red salvo el bucle local."""

from __future__ import annotations

import os
import socket

import httpx
import pytest

from tests.offline import is_local

FIXED = {"EIM_OBS", "EIM_NOTIFY", "EIM_DUCKDB_MEMORY", "EIM_DUCKDB_THREADS"}


def test_no_machine_variable_reaches_the_tests():
    assert {k for k in os.environ if k.upper().startswith("EIM_")} == FIXED
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_outside_hosts_are_refused_at_once():
    with pytest.raises(OSError):
        socket.getaddrinfo("data.binance.vision", 443)
    with pytest.raises(OSError):
        socket.create_connection(("1.1.1.1", 443), timeout=5)
    with pytest.raises(httpx.ConnectError):
        httpx.get("https://data.binance.vision/", timeout=5)


def test_loopback_still_works():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    with socket.create_connection(srv.getsockname(), timeout=5):
        conn, _ = srv.accept()
        conn.close()
    srv.close()


@pytest.mark.parametrize("host,local", [
    ("localhost", True), ("127.0.0.1", True), ("::1", True), ("[::1]", True), ("0.0.0.0", True),
    (None, True), ("api.binance.com", False), ("8.8.8.8", False), ("192.168.1.10", False)])
def test_is_local(host, local):
    assert is_local(host) is local
