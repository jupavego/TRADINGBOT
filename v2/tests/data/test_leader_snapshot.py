"""Instantánea a pedido de `leaders.duckdb` (T115): pedidos que no se pisan y se atienden en
orden, limpieza que solo borra restos y espera que no confunde la cola con un servicio caído."""

import os
import time

import pytest

from eim.data import leader_snapshot as LS
from eim.data.leader_snapshot import request_snapshot, take_snapshot_request, wait_snapshot


def _pending(root) -> list:
    return sorted(p.name for p in (root / "leaders").glob("snapshot_request*"))


def test_two_requesters_never_clobber_and_are_served_in_order(tmp_path):
    a = request_snapshot(tmp_path, 5)
    b = request_snapshot(tmp_path, 5)                       # mismo milisegundo, otro pedido
    (tmp_path / "leaders" / LS.LEGACY_REQ).write_text('{"requested_at": 7}', encoding="utf-8")
    assert a != b and len(_pending(tmp_path)) == 3
    assert [take_snapshot_request(tmp_path) for _ in range(4)] == [
        a, b, LS.snapshot_path(tmp_path, 7), None]          # el pedido de antes de T115, también


def test_cleanup_keeps_a_finished_snapshot_nobody_has_collected_yet(tmp_path):
    d = tmp_path / "leaders"
    d.mkdir()
    fresh, old = d / "snapshot-1.duckdb", d / "snapshot-0.duckdb"
    broken = [d / "snapshot-2.tmp.duckdb", d / "snapshot-2.tmp.duckdb.wal"]
    for p in (fresh, old, *broken):
        p.write_bytes(b"x")
    stale = time.time() - 2 * LS.STALE_S
    os.utime(old, (stale, stale))
    request_snapshot(tmp_path, 3)
    take_snapshot_request(tmp_path)
    assert fresh.exists()                                    # la copia de seguridad la recoge
    assert not old.exists() and not any(p.exists() for p in broken)   # restos


def test_waiting_in_line_behind_a_running_snapshot_is_not_a_dead_service(tmp_path):
    ours = request_snapshot(tmp_path, 10)
    ahead = tmp_path / "leaders" / "snapshot-1.tmp.duckdb"   # la de `copy-sim`, ≈ 5 min
    n = [0]

    def sleep(_s: float) -> None:
        n[0] += 1
        if n[0] < 400:
            ahead.write_bytes(b"x" * n[0])                   # crece: hay avance
        elif n[0] == 400:
            ahead.unlink()
            assert take_snapshot_request(tmp_path) == ours   # ahora nos toca
        else:
            ours.write_bytes(b"lista")

    assert wait_snapshot(tmp_path, ours, sleep=sleep) == ours
    assert n[0] > LS.PICKUP_S


def test_wait_gives_up_without_progress_and_withdraws_the_request(tmp_path):
    snap = request_snapshot(tmp_path, 1)
    with pytest.raises(TimeoutError, match="no atendió"):   # nadie atiende ni hay nada en curso
        wait_snapshot(tmp_path, snap, sleep=lambda s: None)
    assert _pending(tmp_path) == []
    snap = request_snapshot(tmp_path, 2)
    take_snapshot_request(tmp_path)                          # la empieza…
    (tmp_path / "leaders" / "snapshot-2.tmp.duckdb").write_bytes(b"x")   # …y se queda parada
    with pytest.raises(TimeoutError, match="parada"):
        wait_snapshot(tmp_path, snap, sleep=lambda s: None)
