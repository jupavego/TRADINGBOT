"""Cada test usa un emisor propio apuntando a una carpeta temporal."""
from __future__ import annotations

import pytest

import eim.observability.emit as E
from eim.core import Mode


@pytest.fixture(autouse=True)
def _obs_on(monkeypatch):
    """El resto de los tests corren con `EIM_OBS=off` (tests/conftest.py); aquí se observa."""
    monkeypatch.setenv("EIM_OBS", "on")


@pytest.fixture
def spool(tmp_path):
    d = tmp_path / "spool"
    E.configure(process="test", mode=Mode.ANALISIS, spool_dir=d, enabled=True,
                queue_size=10_000)
    yield d
    E.close()
    E.configure(process="eim", spool_dir=tmp_path / "unused", enabled=False)
