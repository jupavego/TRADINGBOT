"""T115: la copia completa desde la API y desde el servicio de operación (copia diaria en un hilo
que no frena el ciclo), la CLI que se la pide a la API y la instantánea del servicio de líderes
que no frena su bucle."""

import asyncio
import threading
from pathlib import Path

import duckdb
from fastapi import FastAPI

from eim.api.backup import build_backup_router
from eim.api.reports_db import ReportStore
from eim.data import backup as B
from eim.data.leader_service import LeaderService
from eim.data.leader_snapshot import request_snapshot
from eim.data.leader_store import LeaderStore
from eim.operation import alerts as A
from tests.data.backup_helpers import ROWS, T0, data, holding
from tests.leaders.helpers import FakeInfo
from tests.local_client import LocalClient
from tests.operation.helpers import Market, Rig

T0_MS = int(T0 * 1000)


def test_api_backup_copies_paper_hot_and_the_rest_cold(tmp_path):
    d = data(tmp_path)
    store = ReportStore(d / B.DB_NAME)
    pcon = duckdb.connect(str(d / B.PAPER))                    # la API tiene paper abierta
    app = FastAPI()
    app.include_router(build_backup_router(store, d, tmp_path / "bk", 3,
                                           extra_dbs={B.PAPER: (pcon, threading.Lock())}))
    try:
        with LocalClient(app) as c:
            r = c.post("/v2/backup", headers={"X-EIM-Confirm": "backup"}).json()
    finally:
        store.close()
        pcon.close()
    assert r["absent"] == {} and r["dbs"][B.PAPER]["tables"]["t"] == ROWS[B.PAPER]
    assert {n: x["via"] for n, x in r["dbs"].items()} == {
        B.DB_NAME: "caliente", B.PAPER: "caliente", B.LEADERS: "frío", B.OBS_NAME: "frío"}
    assert B.verify(Path(r["path"])) == []


def test_daily_backup_runs_beside_the_cycle_and_alerts_when_incomplete(tmp_path, monkeypatch):
    rig = Rig(tmp_path, Market())
    op = rig.build()
    op.backup_dir, op.backup_in_thread = tmp_path / "bk", True
    monkeypatch.setattr(B, "LEADERS_WAIT_S", 4.0)
    duckdb.connect(str(tmp_path / B.LEADERS)).close()
    try:
        with holding(tmp_path / B.LEADERS, "hold"):          # servicio de líderes colgado
            op.step()                                          # toca la copia: arranca el hilo
            assert op._backup_thread.is_alive()
            rig.advance(60_000)
            op.step()                    # el ciclo no espera a la instantánea de líderes
            assert op._backup_thread.is_alive()
            op._backup_thread.join(30)
        (out,) = B.listing(op.backup_dir)
        s = B.summary(out)
        assert B.LEADERS in s["absent"] and B.verify(out) == [] and s["held_s"] < 4
        assert not [a for a in rig.sent if a.kind == A.BACKUP]   # se publica en el ciclo
        rig.advance(60_000)
        op.step()
        (alert,) = [a for a in rig.sent if a.kind == A.BACKUP]
        assert alert.title == "Copia de seguridad incompleta" and B.LEADERS in alert.detail
        assert len(B.listing(op.backup_dir)) == 1                # no se repite ese día
    finally:
        rig.close()
def test_cli_delegates_to_the_api_and_flags_an_api_older_than_t115(tmp_path, monkeypatch,
                                                                    capsys):
    d, bk = data(tmp_path), tmp_path / "bk"
    full = B.summary(B.create(d, bk, clock=lambda: T0))         # lo que devolvería la API nueva
    answers = [full, {"path": full["path"], "name": full["name"], "files": 3, "tables": {}}]
    monkeypatch.setattr(B, "post_local", lambda *a, **k: answers.pop(0))
    argv = ["create", "--data-dir", str(d), "--dest", str(bk)]
    with holding(d / B.DB_NAME, "hold"):                  # la API tiene reports abierta
        assert B.main(argv) == 0
        assert B.main(argv) == 2                           # API vieja: sin paper ni leaders
    assert "anterior a T115" in capsys.readouterr().out


def test_leaders_service_snapshot_runs_beside_its_loop(tmp_path, monkeypatch):
    """La instantánea (≈ 5 min en vivo) no frena el bucle del servicio de líderes."""
    store = LeaderStore.at_root(tmp_path)
    svc = LeaderService(store, FakeInfo([]), [], root=tmp_path, clock=lambda: T0_MS,
                        quote_coins=[])
    gate, real = threading.Event(), store.snapshot
    monkeypatch.setattr(store, "snapshot", lambda p: (gate.wait(10), real(p))[1])
    first = request_snapshot(tmp_path, 1)
    second: list = []

    async def loop() -> None:
        await svc.extra_jobs()                         # arranca la instantánea…
        assert not first.exists() and not svc._snap_task.done()
        await svc.extra_jobs()                         # …y el bucle sigue sin esperarla
        second.append(request_snapshot(tmp_path, 2))
        await svc.extra_jobs()                         # otro pedido aguarda su turno
        assert list((tmp_path / "leaders").glob("snapshot_request*.json"))
        gate.set()
        await svc._snap_task
        await svc.extra_jobs()                         # luego se atiende el segundo
        await svc._snap_task

    try:
        asyncio.run(loop())
        assert first.exists() and second[0].exists()  # la primera, sin recoger, no se borra
    finally:
        store.close()
