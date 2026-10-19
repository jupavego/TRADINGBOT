"""T61: exportación en caliente (base en uso), ruta de la API, CLI y reportes."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI

from eim.api.reports_db import ReportStore
from eim.api.share import build_share_router
from eim.data import share
from eim.data.backup import copy_db_hot
from eim.data.paper_store import PaperStore
from eim.data.share_export import ShareError, export
from eim.data.share_snap import HotSnapshots
from tests.local_client import LocalClient
from tests.share.helpers import M15, NOW, T0, apply, build, publish, rows


def test_export_falls_back_to_hot_snapshot_when_db_in_use(tmp_path):
    b = build(tmp_path, "b", asofs=[T0 + M15, T0 + 2 * M15], report_asofs=[T0, T0 + 1])
    ps = PaperStore(b / "paper.duckdb")              # «la API» tiene la base abierta
    taken: list[str] = []

    class Snap:
        def __call__(self, db: str) -> Path:
            taken.append(db)
            con, lock = ps.connection
            dst = tmp_path / "snap" / db
            dst.parent.mkdir(exist_ok=True)
            copy_db_hot(con, lock, dst)
            return dst

        def close(self) -> None:
            taken.append("closed")

    try:
        with pytest.raises(ShareError, match="en uso"):
            export(b, tmp_path / "cloud0", "b", now=NOW)                  # sin instantánea
        out = export(b, tmp_path / "cloud", "b", snapshotter=Snap(), now=NOW)
    finally:
        ps.close()
    assert taken == ["paper.duckdb", "closed"]
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["tables"]["paper_ctx"]["rows"] == 2 and m["tables"]["reports"]["rows"] == 2
    assert not list((tmp_path / "cloud" / "b").glob(".*.partial"))


def test_snapshot_route_copies_reports_and_paper(tmp_path):
    d = build(tmp_path, "b", asofs=[T0 + M15], report_asofs=[T0])
    rs, ps = ReportStore(d / "reports.duckdb"), PaperStore(d / "paper.duckdb")
    app = FastAPI()
    app.include_router(build_share_router(rs, ps, d))
    try:
        with LocalClient(app) as c:
            assert c.post("/v2/share/snapshot").status_code == 403         # exige X-EIM-Confirm
            res = c.post("/v2/share/snapshot", headers={"X-EIM-Confirm": "share"}).json()
        snap = Path(res["dir"])
        assert sorted(res["files"]) == ["paper.duckdb", "reports.duckdb"]
        assert rows(snap, "paper.duckdb", "SELECT count(*) FROM paper_ctx") == [(1,)]
        assert rows(snap, "reports.duckdb", "SELECT count(*) FROM reports") == [(1,)]
        hot = HotSnapshots(d, "http://x", post=lambda *a, **k: res)
        assert hot("paper.duckdb") == snap / "paper.duckdb"
        hot.close()
        assert not snap.exists()
    finally:
        rs.close()
        ps.close()


def test_cli_export_import_roundtrip(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("EIM_MACHINE", raising=False)
    a = build(tmp_path, "a", asofs=[T0 + M15])
    b = build(tmp_path, "b", asofs=[T0 + M15, T0 + 2 * M15])
    shared = tmp_path / "cloud"
    base = ["--shared-dir", str(shared), "--api", "http://127.0.0.1:1"]
    assert share.main(["export", "--data-dir", str(b), *base]) == 0
    assert share.main(["status", "--data-dir", str(a), *base]) == 0
    out = capsys.readouterr().out
    assert "exportado (b)" in out and "esta máquina: a" in out
    args = ["import", "--data-dir", str(a), "--backup-dir", str(tmp_path / "bk"), *base]
    assert share.main(args) == 0
    assert "SIMULACRO" in capsys.readouterr().out
    assert len(rows(a, "paper.duckdb", "SELECT * FROM paper_ctx")) == 1
    assert share.main([*args, "--apply", "--no-recompute"]) == 0
    assert "IMPORTACIÓN APLICADA" in capsys.readouterr().out
    assert len(rows(a, "paper.duckdb", "SELECT * FROM paper_ctx")) == 2
    assert list((a / "share").glob("import_*.json"))


def test_cli_requires_shared_dir(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("EIM_SHARED_DIR", raising=False)
    assert share.main(["export", "--data-dir", str(tmp_path)]) == 1
    assert "EIM_SHARED_DIR" in capsys.readouterr().err


def test_reports_and_sim_trades_travel(tmp_path):
    a = build(tmp_path, "a", report_asofs=[T0])
    b = build(tmp_path, "b", report_asofs=[T0, T0 + 1, T0 + 2])
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    rep = apply(a, shared, "a")
    assert rep.totals()["reports"] == {"new": 2, "dup": 1, "conflict": 0, "incompatible": 0}
    assert len(rows(a, "reports.duckdb", "SELECT * FROM reports")) == 3
