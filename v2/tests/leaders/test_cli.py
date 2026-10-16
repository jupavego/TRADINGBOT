"""CLI de líderes (T40): validación de direcciones y estados protegidos."""

from __future__ import annotations

import argparse
import sys

from eim.data.leader_store import LeaderStore
from eim.leaders.cli import _supervise, main
from eim.operation.watchdog import instance_lock
from tests.leaders.helpers import TEST, leader


def test_add_invalid_address_and_watch_toggle(tmp_path, capsys):
    main(["--root", str(tmp_path), "add", "0x123"])
    assert "inválida" in capsys.readouterr().out
    main(["--root", str(tmp_path), "add", TEST, "--watch"])
    s = LeaderStore.at_root(tmp_path)
    s.set_status(leader(TEST).id, "approved", 1)
    s.close()
    main(["--root", str(tmp_path), "watch", TEST])  # el veredicto es del scorecard (T41)
    assert "sin cambios (estado approved" in capsys.readouterr().out
    main(["--root", str(tmp_path), "unwatch", TEST])  # dejar de capturar: desde cualquier estado
    s = LeaderStore.at_root(tmp_path)
    assert [ld.status for ld in s.leaders()] == ["candidate"]
    s.close()


def test_supervise_needs_tracked_leaders_and_a_single_instance(tmp_path, capsys):
    root = str(tmp_path)
    main(["--root", root, "supervise"])  # sin líderes en seguimiento: no se vigila nada
    assert "No hay líderes en seguimiento" in capsys.readouterr().out
    main(["--root", root, "add", TEST, "--watch"])
    got = []

    class FakeWatchdog:
        def __init__(self, cmd, env, hb, log, title):
            got.append((cmd, hb, title))

        def run(self):
            assert instance_lock(tmp_path / "leaders" / "supervisor.lock") is None  # tomado

    a = argparse.Namespace(root=root, ws_max=7)
    assert _supervise(a, FakeWatchdog) == "vigilante de líderes detenido"
    ((cmd, hb, title),) = got
    assert cmd == [sys.executable, "-m", "eim.leaders", "--root", root, "run", "--ws-max", "7"]
    assert hb == tmp_path / "leaders" / "heartbeat.json" and "Líderes" in title
    held = instance_lock(tmp_path / "leaders" / "supervisor.lock")  # otro vigilante en marcha
    assert "Ya hay un vigilante" in _supervise(a, FakeWatchdog) and len(got) == 1
    held.close()
