"""T115: la copia cubre las tres bases (y el observatorio), cada una por su camino; una base en
uso por otro proceso no la rompe; restauración probada de verdad; retención de copias completas."""

import json
import os
import subprocess
import sys
import threading
import time

import duckdb
import pytest

from eim.data import backup as B
from eim.data.backup_dbs import DBS, SNAP, count_file, sha256
from tests.data.backup_helpers import ROWS, T0, V2, content, data, holding, manifest


def test_full_backup_delete_restore_same_rows_and_sha256(tmp_path):
    d, bk = data(tmp_path), tmp_path / "bk"
    want = {n: count_file(d / DBS[n]) for n in DBS}
    rows = {n: content(d / DBS[n]) for n in DBS}
    out = B.create(d, bk, clock=lambda: T0)
    m = manifest(out)
    assert m["format"] == 2 and m["absent"] == {}
    assert list(m["dbs"]) == [B.DB_NAME, B.PAPER, B.LEADERS, B.OBS_NAME]
    assert {n: x["tables"] for n, x in m["dbs"].items()} == want
    assert {x["via"] for x in m["dbs"].values()} == {"frío"}
    assert B.verify(out) == []
    for n in DBS:                                              # el equipo pierde las bases
        (d / DBS[n]).unlink()
    assert B.restore(out, d, clock=lambda: T0) == [B.DB_NAME, B.PAPER, B.LEADERS, B.OBS_NAME,
                                                   "kill_switch.json", "operation/"]
    for n in DBS:
        assert sha256(d / DBS[n]) == m["files"][n]["sha256"]      # idéntica a la copia
        assert count_file(d / DBS[n]) == want[n] and content(d / DBS[n]) == rows[n]
    assert json.loads((d / "operation" / "state_paper.json").read_text()) == {"cursor": 1}


def test_restore_replaces_whole_and_keeps_the_previous_aside(tmp_path):
    d = data(tmp_path)
    out = B.create(d, tmp_path / "bk", clock=lambda: T0)
    con = duckdb.connect(str(d / B.PAPER))
    con.execute("INSERT INTO t VALUES (99, 'posterior a la copia')")
    con.close()
    B.restore(out, d, clock=lambda: T0)
    assert count_file(d / B.PAPER)["t"] == ROWS[B.PAPER]               # no se mezcla
    aside = d / (B.PAPER + ".antes-de-restaurar-20261014-174640")
    assert count_file(aside)["t"] == ROWS[B.PAPER] + 1                  # ni se pierde


def test_leaders_in_use_is_copied_through_the_service_and_blocks_restore(tmp_path):
    d, bk = data(tmp_path), tmp_path / "bk"
    with holding(d / B.LEADERS, "serve"):                 # el servicio de líderes en marcha
        out = B.create(d, bk, clock=lambda: T0)
        m = manifest(out)
        assert m["dbs"][B.LEADERS]["via"] == SNAP and m["absent"] == {}
        assert m["dbs"][B.LEADERS]["tables"]["t"] == ROWS[B.LEADERS]
        assert B.verify(out) == []
        assert not list((d / "leaders").glob("snapshot*"))          # la instantánea se movió
        before = {n: sha256(d / DBS[n]) for n in (B.DB_NAME, B.PAPER)}
        with pytest.raises(B.BackupError, match="detén la API.*leaders.duckdb.*no se ha tocado"):
            B.restore(out, d)
        assert {n: sha256(d / DBS[n]) for n in before} == before        # nada cambió
        assert not list(d.rglob("*antes-de-restaurar*"))


def test_hung_leaders_service_leaves_it_absent_and_verify_tells_it_from_damage(tmp_path,
                                                                                capsys):
    d, bk = data(tmp_path), tmp_path / "bk"
    with holding(d / B.LEADERS, "hold"):                  # en uso y sin nadie que responda
        out = B.create(d, bk, clock=lambda: T0, leaders_wait_s=3, sleep=lambda s: None)
        assert not list((d / "leaders").glob("snapshot_request*"))   # pedido retirado
    m = manifest(out)
    assert B.LEADERS not in m["dbs"] and "no entregó la instantánea" in m["absent"][B.LEADERS]
    assert set(m["dbs"]) == {B.DB_NAME, B.PAPER, B.OBS_NAME}
    assert B.verify(out) == [] and not B.summary(out)["dbs"].get(B.LEADERS)
    capsys.readouterr()
    assert B.main(["verify", str(out)]) == 2                        # íntegra pero incompleta
    assert "AUSENTE" in capsys.readouterr().out
    local = sha256(d / B.LEADERS)
    assert B.restore(out, d, clock=lambda: T0)[:3] == [B.DB_NAME, B.PAPER, B.OBS_NAME]
    assert sha256(d / B.LEADERS) == local                           # la ausente no se toca
    (out / B.PAPER).unlink()                                         # daño de verdad
    assert B.verify(out) == [f"falta {B.PAPER}"]
    assert B.main(["verify", str(out)]) == 1


def test_api_db_in_use_strict_asks_the_api_lenient_marks_it_absent(tmp_path, capsys):
    d, bk = data(tmp_path), tmp_path / "bk"
    with holding(d / B.PAPER, "hold"):                    # «la API» tiene paper abierta
        with pytest.raises(B.DbBusy, match="paper.duckdb en uso"):
            B.create(d, bk, clock=lambda: T0)
        assert not (d / "leaders").exists()          # falla antes de pedir nada a los líderes
        assert B.listing(bk) == [] and not list(bk.glob(".*.partial"))
        out = B.create(d, bk, clock=lambda: T0, strict=False)
        assert B.main(["create", "--data-dir", str(d), "--dest", str(bk),
                       "--api", "http://127.0.0.1:9"]) == 2                # sin API en marcha
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}  # salida redirigida en Windows
        r = subprocess.run([sys.executable, "-m", "eim.data.backup", "create", "--data-dir", str(d),
                            "--dest", str(bk), "--api", "http://127.0.0.1:9"], cwd=V2, env=env,
                           capture_output=True)
        assert r.returncode == 2, r.stderr.decode(errors="replace")    # «→» no la rompe
    assert manifest(out)["absent"][B.PAPER].startswith("en uso por otro proceso")
    assert "la API no respondió" in capsys.readouterr().out
    assert [B.summary(p)["absent"] != {} for p in B.listing(bk)] == [True] * 3


def test_damaged_db_is_absent_and_not_taken_for_in_use(tmp_path):
    d = data(tmp_path)
    (d / B.LEADERS).write_bytes(b"no es una base")
    out = B.create(d, tmp_path / "bk", clock=lambda: T0, sleep=lambda s: None)
    assert manifest(out)["absent"][B.LEADERS].startswith("no se puede abrir")
    assert not list((d / "leaders").glob("snapshot_request*"))  # no se pidió instantánea


def test_hot_copy_is_consistent_while_writers_keep_writing(tmp_path):
    con, lock = duckdb.connect(str(tmp_path / "x.duckdb")), threading.Lock()
    con.execute("CREATE TABLE a AS SELECT i FROM range(300000) r(i)")
    con.execute("CREATE TABLE b AS SELECT i FROM range(300000) r(i)")
    stop = threading.Event()

    def writer():                                  # cada transacción mantiene a = b
        while not stop.is_set():
            with lock:
                con.execute("BEGIN")
                con.execute("INSERT INTO a SELECT i FROM range(100) r(i)")
                con.execute("INSERT INTO b SELECT i FROM range(100) r(i)")
                con.execute("COMMIT")

    w = threading.Thread(target=writer)
    w.start()
    try:
        got = B.copy_db_hot(con, lock, tmp_path / "copia.duckdb")
    finally:
        stop.set()
        w.join()
        con.close()
    assert got["a"] == got["b"] >= 300000


def test_retention_counts_complete_copies_and_never_keeps_partials(tmp_path):
    d, bk = data(tmp_path), tmp_path / "bk"
    outs = [B.create(d, bk, keep=0, clock=lambda i=i: T0 + i * 86_400) for i in range(5)]
    for p in outs[2:]:                                    # las tres últimas, incompletas
        m = manifest(p)
        m["absent"] = {B.LEADERS: "prueba"}
        (p / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    stale, fresh = bk / ".eim_20261001-000000.partial", bk / ".eim_20261019-000000.partial"
    for p in (stale, fresh):
        p.mkdir()
        (p / B.DB_NAME).write_bytes(b"a medias")
    old = time.time() - 2 * B.PARTIAL_STALE_S
    for p in (stale / B.DB_NAME, stale):
        os.utime(p, (old, old))
    B.prune(bk, 2)
    # 2 completas más recientes (0, 1) + 2 más recientes de cualquier tipo (3, 4)
    assert B.listing(bk) == [outs[0], outs[1], outs[3], outs[4]]
    assert not stale.exists() and fresh.exists()          # la reciente puede estar en curso


def test_reads_t32_manifests(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    con = duckdb.connect(str(d / B.DB_NAME))
    con.execute("CREATE TABLE t AS SELECT 1 AS x")
    con.close()
    out = B.create(d, tmp_path / "bk", clock=lambda: T0)
    m = manifest(out)
    old = {k: v for k, v in m.items() if k not in ("format", "dbs", "absent")}
    old["tables"], old["extra_tables"] = m["dbs"][B.DB_NAME]["tables"], {}
    (out / "manifest.json").write_text(json.dumps(old), encoding="utf-8")
    assert B.verify(out) == [] and B.summary(out)["dbs"][B.DB_NAME]["tables"] == {"t": 1}
    assert B.restore(out, d, clock=lambda: T0) == [B.DB_NAME]
