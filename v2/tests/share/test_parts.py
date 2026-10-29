"""T117: una tabla grande viaja en partes (el transporte git no admite archivos de > 90 MB)."""

import json

from eim.data.share_export import export
from eim.data.share_import import import_all
from tests.share.helpers import M15, NOW, T0, apply, build, rows

VERSIONS = [("s@15m", n, f"fp{n}", n - 1 or None, None) for n in range(1, 5)]


def _big(tmp_path):
    a = build(tmp_path, "a", asofs=[T0 + M15])
    b = build(tmp_path, "b", asofs=[T0 + i * M15 for i in range(1, 40)], fills=range(1, 60),
              versions=VERSIONS, windows=[("s@15m", n, T0, T0 + n) for n in range(1, 5)])
    shared = tmp_path / "cloud"
    return a, b, shared, export(b, shared, "b", now=NOW, part_bytes=1000)


def _manifest(out):
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


def test_big_tables_travel_in_parts_and_merge_whole(tmp_path):
    a, b, shared, out = _big(tmp_path)
    tabs = _manifest(out)["tables"]
    for name, n in (("leader_fills", 59), ("paper_ctx", 39), ("val_versions", 4)):
        parts = tabs[name]["parts"]
        assert len(parts) >= 2 and sum(p["rows"] for p in parts) == tabs[name]["rows"] == n
        assert not (out / f"{name}.parquet").exists() and "file" not in tabs[name]
    rep = apply(a, shared, "a")
    tot = rep.totals()
    assert not rep.rejected and tot["leader_fills"]["new"] == 59
    assert tot["paper_ctx"] == {"new": 38, "dup": 1, "conflict": 0, "incompatible": 0}
    assert tot["val_versions"]["new"] == 4 and tot["val_windows"]["new"] == 4
    assert rows(a, "leaders.duckdb", "SELECT count(DISTINCT tid) FROM leader_fills") == [(59,)]
    again = apply(a, shared, "a").totals()                  # idempotente con partes
    assert again["leader_fills"] == {"new": 0, "dup": 59, "conflict": 0, "incompatible": 0}
    assert again["val_versions"]["new"] == 0


def test_tampered_or_missing_part_rejects_whole_export(tmp_path):
    a, b, shared, out = _big(tmp_path)
    parts = _manifest(out)["tables"]["leader_fills"]["parts"]
    f = out / parts[-1]["file"]
    f.write_bytes(f.read_bytes() + b"x")
    rep = apply(a, shared, "a")
    assert rep.rejected and "hash distinto" in " ".join(rep.rejected[0]["problems"])
    f.unlink()                                  # la nube aún no trajo esa parte
    rep = apply(a, shared, "a")
    assert any(f"falta {parts[-1]['file']}" in p for p in rep.rejected[0]["problems"])
    assert not rep.results and rows(a, "leaders.duckdb", "SELECT count(*) FROM leader_fills") \
        == [(0,)]


def test_old_format_still_imports_and_newer_is_rejected(tmp_path):
    a = build(tmp_path, "a", asofs=[T0 + M15])
    b = build(tmp_path, "b", asofs=[T0 + 2 * M15])
    shared = tmp_path / "cloud"
    out = export(b, shared, "b", now=NOW)                   # tablas pequeñas: un archivo
    m = _manifest(out)
    assert "file" in m["tables"]["paper_ctx"] and "parts" not in m["tables"]["paper_ctx"]
    m["format"] = 1                                         # exportación previa a T117
    (out / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    sim = import_all(a, shared, "a")
    assert not sim.rejected and sim.totals()["paper_ctx"]["new"] == 1
    m["format"] = 99
    (out / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    rep = import_all(a, shared, "a")
    assert rep.rejected and "actualiza el código" in rep.rejected[0]["problems"][0]
