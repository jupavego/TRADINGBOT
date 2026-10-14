"""T32: copias de seguridad del almacén y la configuración (frío, caliente, verificación,
restauración, poda, API y copia diaria del servicio)."""

import json
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pytest
from fastapi import FastAPI

from eim.api.backup import build_backup_router
from eim.api.reports_db import ReportStore
from eim.data import backup as B
from eim.operation import alerts as A
from eim.operation.supervisor import BACKUP_RETRY_MS
from tests.local_client import LocalClient
from tests.operation.helpers import Market, Rig

T0 = 1_792_000_000.0          # 2026-10-14 (UTC)


def _data(tmp_path):
    d = tmp_path / "data"
    (d / "operation" / "logs").mkdir(parents=True)
    con = duckdb.connect(str(d / B.DB_NAME))
    con.execute("CREATE TABLE t (x INT)")
    con.execute("INSERT INTO t VALUES (1), (2), (3)")
    con.close()
    (d / "kill_switch.json").write_text('{"active": false}', encoding="utf-8")
    (d / "operation" / "heartbeat.json").write_text("{}", encoding="utf-8")
    (d / "operation" / "logs" / "op-2026-10-14.jsonl").write_text("{}\n", encoding="utf-8")
    (d / "candles").mkdir()
    (d / "candles" / "x.parquet").write_bytes(b"PAR1")
    return d


def test_cold_backup_and_verify(tmp_path):
    d = _data(tmp_path)
    out = B.create(d, tmp_path / "bk", clock=lambda: T0)
    assert out.name.startswith("eim_20261014-")
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["tables"] == {"t": 3}
    assert {"reports.duckdb", "state/kill_switch.json", "state/operation/heartbeat.json",
            "state/operation/logs/op-2026-10-14.jsonl",
            "config/risk/risk_v1.json"} <= set(m["files"])
    assert not any(k.startswith("market/") for k in m["files"])      # sin --with-market
    assert B.verify(out) == []


def test_with_market(tmp_path):
    out = B.create(_data(tmp_path), tmp_path / "bk", with_market=True, clock=lambda: T0)
    assert (out / "market" / "candles" / "x.parquet").read_bytes() == b"PAR1"


def test_verify_detects_tampering(tmp_path):
    out = B.create(_data(tmp_path), tmp_path / "bk", clock=lambda: T0)
    (out / "state" / "kill_switch.json").write_text('{"active": true}', encoding="utf-8")
    assert B.verify(out) == ["hash distinto: state/kill_switch.json"]
    (out / "manifest.json").unlink()
    assert B.verify(out) == ["falta manifest.json"]


def test_hot_backup_while_db_open(tmp_path):
    d = _data(tmp_path)
    store = ReportStore(d / B.DB_NAME)          # la API la tiene abierta
    try:
        with pytest.raises(B.BackupError):
            B.create(d, tmp_path / "bk", clock=lambda: T0)
        assert B.listing(tmp_path / "bk") == []                     # sin copias a medias
        con, lock = store.connection
        out = B.create(d, tmp_path / "bk", con=con, lock=lock, clock=lambda: T0)
        assert B.verify(out) == []
        assert json.loads((out / "manifest.json").read_text())["tables"]["t"] == 3
        con.execute("INSERT INTO t VALUES (4)")                     # la base sigue utilizable
    finally:
        store.close()


def test_prune_and_due_today(tmp_path):
    d, bk = _data(tmp_path), tmp_path / "bk"
    assert B.due_today(bk, T0)
    for i in range(4):
        B.create(d, bk, keep=2, clock=lambda i=i: T0 + i * 86_400)
    names = [p.name for p in B.listing(bk)]
    assert len(names) == 2 and names[-1].startswith("eim_20261017")
    assert not B.due_today(bk, T0 + 3 * 86_400) and B.due_today(bk, T0 + 4 * 86_400)


def test_restore(tmp_path):
    d = _data(tmp_path)
    out = B.create(d, tmp_path / "bk", clock=lambda: T0)
    con = duckdb.connect(str(d / B.DB_NAME))
    con.execute("DELETE FROM t")
    con.close()
    (d / "kill_switch.json").write_text('{"active": true}', encoding="utf-8")
    (d / "operation" / "state_testnet.json").write_text("{}", encoding="utf-8")  # no copiado
    assert B.restore(out, d, clock=lambda: T0) == ["reports.duckdb", "kill_switch.json",
                                                   "operation/"]
    con = duckdb.connect(str(d / B.DB_NAME), read_only=True)
    assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 3
    con.close()
    assert json.loads((d / "kill_switch.json").read_text())["active"] is False
    assert not (d / "operation" / "state_testnet.json").exists()            # sin restos
    assert (d / "operation.antes-de-restaurar-20261014-174640" / "state_testnet.json").exists()
    assert (d / "reports.duckdb.antes-de-restaurar-20261014-174640").exists()
    B.restore(out, d, clock=lambda: T0 + 60)              # segunda restauración: no pisa la 1.ª
    assert (d / "reports.duckdb.antes-de-restaurar-20261014-174640").exists()
    assert (d / "reports.duckdb.antes-de-restaurar-20261014-174740").exists()


def test_paths_with_quotes(tmp_path):
    root = tmp_path / "D'Angelo"
    d = _data(root)
    out = B.create(d, root / "bk", clock=lambda: T0)                      # copia en frío
    assert B.verify(out) == []
    store = ReportStore(d / B.DB_NAME)
    try:
        con, lock = store.connection
        hot = B.create(d, root / "bk", con=con, lock=lock, clock=lambda: T0 + 1)
        assert B.verify(hot) == []
    finally:
        store.close()


def test_restore_refuses_open_db_or_corrupt_copy(tmp_path):
    d = _data(tmp_path)
    out = B.create(d, tmp_path / "bk", clock=lambda: T0)
    with _other_process_holding(d / B.DB_NAME):                       # la API en marcha
        with pytest.raises(B.BackupError, match="detén la API"):
            B.restore(out, d)
        with pytest.raises(B.BackupError, match="en uso"):
            B.create(d, tmp_path / "bk2", clock=lambda: T0)
    (out / B.DB_NAME).write_bytes(b"x")
    with pytest.raises(B.BackupError, match="no íntegra"):
        B.restore(out, d)


@contextmanager
def _other_process_holding(db):
    code = ("import duckdb,sys,time; c=duckdb.connect(sys.argv[1]); print('ok', flush=True); "
            "time.sleep(60)")
    p = subprocess.Popen([sys.executable, "-c", code, str(db)], stdout=subprocess.PIPE,
                         text=True)
    try:
        assert p.stdout.readline().strip() == "ok"
        yield
    finally:
        p.kill()
        p.wait()


def test_cli_create_verify_list(tmp_path, capsys):
    d, bk = _data(tmp_path), tmp_path / "bk"
    assert B.main(["create", "--data-dir", str(d), "--dest", str(bk)]) == 0
    assert B.main(["verify", "--dest", str(bk)]) == 0
    assert "íntegra" in capsys.readouterr().out
    assert B.main(["list", "--dest", str(bk)]) == 0


def test_cli_defaults_follow_env(tmp_path, monkeypatch, capsys):
    d, bk = _data(tmp_path), tmp_path / "otra_unidad"
    monkeypatch.setenv("EIM_DATA_DIR", str(d))
    monkeypatch.setenv("EIM_BACKUP_DIR", str(bk))
    monkeypatch.setenv("EIM_BACKUP_KEEP", "1")
    assert B.main(["create"]) == 0 and B.main(["create"]) == 0
    assert len(B.listing(bk)) == 1                                       # keep=1 del entorno
    capsys.readouterr()
    assert B.main(["list"]) == 0
    assert str(bk) in capsys.readouterr().out


def test_api_backup_requires_confirm(tmp_path):
    d = _data(tmp_path)
    store = ReportStore(d / B.DB_NAME)
    app = FastAPI()
    app.include_router(build_backup_router(store, d, tmp_path / "bk", keep=3))
    try:
        with LocalClient(app) as c:
            assert c.post("/v2/backup").status_code == 403                # sin cabecera
            r = c.post("/v2/backup", headers={"X-EIM-Confirm": "backup"}).json()
            assert r["tables"]["t"] == 3 and r["files"] >= 3
            assert c.get("/v2/backup").json()["backups"] == [r["name"]]
            assert B.verify(Path(r["path"])) == []
    finally:
        store.close()


def test_api_backup_waits_for_operation_cycle(tmp_path):
    rig = Rig(tmp_path, Market())
    op = rig.build()
    op.backup_dir = tmp_path / "bk"
    app = FastAPI()
    app.include_router(build_backup_router(rig.reports, tmp_path, tmp_path / "bk", 3,
                                           lambda: op))
    try:
        with LocalClient(app) as c:
            op._step_lock.acquire()                                       # ciclo en curso
            res = {}
            t = threading.Thread(target=lambda: res.update(r=c.post(
                "/v2/backup", headers={"X-EIM-Confirm": "backup"})))
            t.start()
            t.join(0.5)
            assert t.is_alive() and B.listing(op.backup_dir) == []
            op._step_lock.release()
            t.join(20)
            assert res["r"].status_code == 200
            assert B.listing(op.backup_dir)[0].name == res["r"].json()["name"]
    finally:
        rig.close()


def test_service_daily_backup_and_failure_alert(tmp_path, monkeypatch):
    rig = Rig(tmp_path, Market())
    op = rig.build()
    try:
        op.backup_dir = tmp_path / "bk"
        op.step()
        (first,) = B.listing(op.backup_dir)
        assert B.verify(first) == []
        rig.advance(3_600_000)
        op.step()
        assert len(B.listing(op.backup_dir)) == 1                        # una por día UTC
        op.backup_dir.rename(tmp_path / "bk_old")
        op.backup_dir.write_text("no es carpeta", encoding="utf-8")      # fallo forzado
        rig.advance(86_400_000)
        op.step()
        fails = [a for a in rig.sent if a.kind == A.BACKUP and not a.resolved]
        assert len(fails) == 1
        op.backup_dir.unlink()
        calls, orig = [], B.create
        monkeypatch.setattr(B, "create", lambda *a, **k: calls.append(1) or orig(*a, **k))
        rig.advance(60_000)
        op.step()                                      # dentro de la espera: no reintenta
        assert calls == []
        rig.advance(BACKUP_RETRY_MS)
        op.step()
        assert calls == [1]
        assert len([a for a in rig.sent if a.kind == A.BACKUP and not a.resolved]) == 1
        assert any(a.kind == A.BACKUP and a.resolved for a in rig.sent)
    finally:
        rig.close()


def test_lock_is_honoured(tmp_path):
    d = _data(tmp_path)
    store = ReportStore(d / B.DB_NAME)
    con, _ = store.connection
    lock = threading.Lock()
    lock.acquire()
    t = threading.Thread(target=B.create, args=(d, tmp_path / "bk"),
                         kwargs={"con": con, "lock": lock, "clock": lambda: T0})
    t.start()
    t.join(0.3)
    assert t.is_alive() and B.listing(tmp_path / "bk") == []        # espera al escritor
    lock.release()
    t.join(10)
    assert len(B.listing(tmp_path / "bk")) == 1
    store.close()
