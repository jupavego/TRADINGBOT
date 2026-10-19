"""Máquinas de prueba para T61: dos carpetas de datos con historiales distintos y solapados."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from eim.api.forecast_db import ForecastStore
from eim.api.reports_db import ReportStore
from eim.core.leaders import LeaderFill
from eim.data.leader_store import LeaderStore
from eim.data.paper_store import PaperStore
from eim.data.share_export import export
from eim.data.share_import import import_all
from eim.data.validation_store import ValidationStore
from eim.execution.sim_ledger import SimLedger
from tests.leaders.helpers import TEST, leader

LID = f"hyperliquid:{TEST}"
T0 = 1_792_000_000_000
M15 = 900_000
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def ctx(asof: int, x: int = 1) -> dict:
    return {"t": asof, "v": 1, "x": x}


def fill(tid: int, observed: int = 0) -> LeaderFill:
    return LeaderFill(leader_id=LID, address=TEST, symbol="BTC", side="long", action="open",
                      size=1.0, price=50_000.0, start_position=0.0, end_position=1.0, fee=0.1,
                      tid=tid, oid=tid, t=T0 + tid * 1000, observed_at=T0 + tid * 1000 + observed,
                      channel="ws", source="test")


def version_row(sid: str, n: int, fp: str, parent, retired=None) -> list:
    st, tf = sid.split("@")
    return [sid, n, fp, st, tf, T0 + n, parent, "auto", "", retired]


def build(root: Path, name: str, *, asofs=(), conflict_at=None, versions=(), windows=(),
          fills=(), photos=(), journal=(), recon=0, report_asofs=(), created=10) -> Path:
    """Crea `root/name/data` con lo indicado. `versions`: tuplas (sid, n, fp, parent, retired);
    `windows`: (sid, n, from, to); `photos`: observed_at de fotos de posiciones del líder."""
    d = root / name / "data"
    d.mkdir(parents=True)
    (d / "machine_id").write_text(name + "\n", encoding="utf-8")
    ps = PaperStore(d / "paper.duckdb")
    vs = ValidationStore(ps)
    for a in asofs:
        ps.save("BTCUSDT", "15m", ctx(a, 99 if a == conflict_at else 1), "vivo", created)
    for v in versions:
        ps.execute("INSERT INTO val_versions VALUES (?,?,?,?,?,?,?,?,?,?)",
                   version_row(v[0], v[1], v[2], v[3], v[4]))
    for sid, n, a, b in windows:
        ps.execute("INSERT INTO val_windows VALUES (?,?,?,?,?,?)", [sid, n, a, b, None, "w"])
    vs.save_verdicts("v1", "BTCUSDT", T0, T0, [{"sid": "s@15m", "n": 1, "fingerprint": "x",
                                                "verdict": "OBS", "n_oos": 0, "p_raw": None,
                                                "p_holm": None}])
    ps.close()
    rs = ReportStore(d / "reports.duckdb")
    ForecastStore(*rs.connection)
    SimLedger(*rs.connection)
    con, lock = rs.connection
    for a in report_asofs:
        con.execute("INSERT INTO reports VALUES ('BTCUSDT','15m','trend','1',?,0.1,0.5,'ok','{}')",
                    [a])
    rs.close()
    ls = LeaderStore(d / "leaders.duckdb")
    ls.upsert_leader(leader(), T0)
    ls.add_fills([fill(t, 7 if name == "b" else 3) for t in fills])
    for o in photos:
        ls.query("INSERT OR IGNORE INTO leader_positions VALUES (?,?,?,?)",
                 [LID, o, o, json.dumps([])])
    for i, txt in enumerate(journal, 1):
        ls.query("INSERT INTO copy_journal VALUES (?,?,?,?,?,?,?,?)",
                 [LID, i, T0 + i, "orden", "BTC", "ok", txt, "{}"])
    for i in range(recon):
        ls.query("INSERT INTO leader_recon VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 [LID, T0 + i, T0 + i, 1, 0, True, True, False, None, 0, 0, name])
    ls.close()
    (d / "kill_switch.json").write_text(json.dumps({"active": name == "b"}), encoding="utf-8")
    return d


def publish(d: Path, shared: Path, machine: str) -> Path:
    return export(d, shared, machine, now=NOW)


def apply(d: Path, shared: Path, machine: str, **kw):
    return import_all(d, shared, machine, apply=True, backup_dir=d.parent / "bk", **kw)


def rows(d: Path, db: str, sql: str) -> list[tuple]:
    con = duckdb.connect(str(d / db), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()
