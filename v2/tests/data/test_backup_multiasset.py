"""T102 — la copia diaria guarda el catálogo, la base del escáner y sus resúmenes; con el escáner
en marcha su base queda ausente con motivo y la copia sigue completa."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("duckdb")

from eim.data import backup as B  # noqa: E402
from eim.data.backup_multiasset import DIR  # noqa: E402
from eim.data.instruments_store import open_store  # noqa: E402
from eim.data.scanner_store import open_scanner_store  # noqa: E402
from tests.scanner._helpers import T0, perp  # noqa: E402

CLOCK = 1_795_700_000.0


def _data(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    cat = open_store(d)
    cat.upsert([perp("AUSDT"), perp("BUSDT")], t=T0)
    cat.close()
    open_scanner_store(d).close()
    (d / "scanner" / "view.json").write_text(json.dumps({"mode": "ANALISIS"}), encoding="utf-8")
    (d / "scanner" / "health.json").write_text("{}", encoding="utf-8")
    return d


def test_backup_includes_catalog_scanner_and_summaries(tmp_path):
    out = B.create(_data(tmp_path), tmp_path / "bk", clock=lambda: CLOCK)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    multi = m["multiasset"]
    assert set(multi["dbs"]) == {"instruments.duckdb", "scanner.duckdb"} and multi["absent"] == {}
    assert set(multi["summaries"]) == {"view.json", "health.json"}
    assert f"{DIR}/view.json" in m["files"] and f"{DIR}/instruments.duckdb" in m["files"]
    assert B.verify(out) == [] and m["absent"] == {}


def test_a_running_scanner_leaves_its_base_absent_with_a_reason(tmp_path):
    d = _data(tmp_path)
    busy = open_scanner_store(d)                          # el escáner la tiene abierta
    try:
        out = B.create(d, tmp_path / "bk", clock=lambda: CLOCK)
    finally:
        busy.close()
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert "scanner.duckdb" in m["multiasset"]["absent"]
    assert "instruments.duckdb" in m["multiasset"]["dbs"]
    assert m["absent"] == {} and B.verify(out) == []      # sigue siendo una copia completa


def test_without_a_scanner_nothing_is_added(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    out = B.create(d, tmp_path / "bk", clock=lambda: CLOCK)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["multiasset"] == {"dbs": {}, "absent": {}, "summaries": []}
    assert not (out / DIR).exists()
