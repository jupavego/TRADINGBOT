"""CLI de líderes (T40): validación de direcciones y estados protegidos."""

from __future__ import annotations

from eim.data.leader_store import LeaderStore
from eim.leaders.cli import main
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
