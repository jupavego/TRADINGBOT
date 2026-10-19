"""Cada test usa un emisor propio apuntando a una carpeta temporal."""
from __future__ import annotations

import pytest

import eim.observability.emit as E


@pytest.fixture
def spool(tmp_path):
    d = tmp_path / "spool"
    E.configure(process="test", spool_dir=d, enabled=True, queue_size=10_000)
    yield d
    E.close()
    E.configure(process="eim", spool_dir=tmp_path / "unused", enabled=False)
