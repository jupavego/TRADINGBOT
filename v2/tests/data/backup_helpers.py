"""Ayudas de las pruebas de copias completas (T115): datos con las tres bases y un proceso
aparte que las tiene abiertas."""

import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import duckdb

from eim.data import backup as B
from eim.data.backup_dbs import DBS

V2 = Path(__file__).resolve().parents[2]
T0 = 1_792_000_000.0                      # 2026-10-14 (UTC)
ROWS = {B.DB_NAME: 3, B.PAPER: 5, B.LEADERS: 7, B.OBS_NAME: 2}

# Un proceso aparte con la base abierta: «serve» imita al servicio de líderes (atiende el pedido
# de instantánea con el código real, `LeaderStore.snapshot`); «hold» la retiene sin responder.
HOLDER = """
import sys, time
from pathlib import Path
db, mode = Path(sys.argv[1]), sys.argv[2]
if mode == "serve":
    from eim.data.leader_snapshot import take_snapshot_request
    from eim.data.leader_store import LeaderStore
    st = LeaderStore(db)
else:
    import duckdb
    con = duckdb.connect(str(db))
print("ok", flush=True)
end = time.monotonic() + 120
while time.monotonic() < end:
    snap = take_snapshot_request(db.parent) if mode == "serve" else None
    if snap is not None:
        st.snapshot(snap)
    time.sleep(0.05)
"""


def data(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    (d / "operation").mkdir(parents=True)
    for name, n in ROWS.items():
        p = d / DBS[name]
        p.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(p))
        con.execute("CREATE TABLE t (x INT, s VARCHAR)")
        con.execute(f"INSERT INTO t SELECT i, 'fila ' || i FROM range({n}) r(i)")
        con.execute("CREATE TABLE u (k VARCHAR)")
        con.execute("INSERT INTO u VALUES ('a'), ('b')")
        con.close()
    (d / "kill_switch.json").write_text('{"active": false}', encoding="utf-8")
    (d / "operation" / "state_paper.json").write_text('{"cursor": 1}', encoding="utf-8")
    return d


def content(p: Path) -> list:
    con = duckdb.connect(str(p), read_only=True)
    try:
        return con.execute("SELECT * FROM t ORDER BY x").fetchall()
    finally:
        con.close()


def manifest(out: Path) -> dict:
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


@contextmanager
def holding(db: Path, mode: str):
    p = subprocess.Popen([sys.executable, "-c", HOLDER, str(db), mode], cwd=V2,
                         stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "ok"
        yield
    finally:
        p.kill()
        p.wait()


