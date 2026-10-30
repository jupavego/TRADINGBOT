"""T125: comprobación de arranque — bloquea lo que no debe continuar (sin datos, datos más viejos
que lo publicado, dos equipos con la misma identidad, central inalcanzable) y nunca escribe en
las bases."""

import json
import platform
from datetime import UTC, datetime, timedelta

import pytest

from eim.continuity import check as C
from eim.continuity import datastate, offsite
from tests.continuity.helpers import FakeReleases, backup, repo, run


def _levels(r, area=None):
    return [(f.level, f.text) for f in r.findings if area is None or f.area == area]


def _publish_meta(t, machine, host, rows, hours_ago=1.0):
    """Una copia remota «completa» de mentira con esas filas."""
    name = f"{machine}__eim_20261030-000000"
    (t.root / f"{name}.zip.000").write_bytes(b"z")
    when = (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()
    meta = {"format": offsite.FORMAT, "machine": machine, "backup": "eim_20261030-000000",
            "host": host, "published_at": when, "dbs": {db: {"tables": t_} for db, t_ in
                                                        rows.items()},
            "parts": [{"name": f"{name}.zip.000", "bytes": 1, "sha256": "x"}]}
    (t.root / f"{name}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


@pytest.fixture
def clone(tmp_path):
    c, _ = repo(tmp_path)
    return c


def test_empty_data_blocks_and_explains(tmp_path, clone):
    r = C.run(clone / "v2", tmp_path / "vacio", tmp_path / "bk", network=False)
    assert r.verdict == ("NO SINCRONIZADO", 1)
    [(lvl, text)] = [x for x in _levels(r, "datos") if x[0] == C.BLOCK]
    assert "bases VACÍAS" in text
    assert not (tmp_path / "vacio" / "reports.duckdb").exists()     # no crea nada
    out = C.record(r, tmp_path / "vacio")
    assert json.loads(out.read_text(encoding="utf-8"))["verdict"] == "NO SINCRONIZADO"
    assert "VEREDICTO: NO SINCRONIZADO" in C.render(r)


def test_offline_with_data_warns_but_never_says_up_to_date(tmp_path, clone):
    d, _ = backup(tmp_path)
    r = C.run(clone / "v2", d, tmp_path / "src" / "backups", network=False)
    assert r.level == C.WARN
    assert any("sin red" in t for _, t in _levels(r, "central"))
    assert any("paper.duckdb" in t and "7 filas" in t for _, t in _levels(r, "datos"))


def test_unreachable_central_blocks(tmp_path, clone):
    d, _ = backup(tmp_path)
    run("remote", "set-url", "origin", str(tmp_path / "no-existe.git"), cwd=clone)
    r = C.run(clone / "v2", d, tmp_path / "src" / "backups",
              transport=FakeReleases(tmp_path / "gh"))
    assert r.level == C.BLOCK
    assert any("sincronización NO completada" in t for _, t in _levels(r, "central"))


def test_data_older_than_own_published_copy_blocks(tmp_path, clone):
    d, _ = backup(tmp_path)
    (d / "machine_id").write_text("equipo-a\n", encoding="utf-8")
    t = FakeReleases(tmp_path / "gh")
    _publish_meta(t, "equipo-a", platform.node(), {"paper.duckdb": {"t": 500, "u": 2}})
    r = C.run(clone / "v2", d, tmp_path / "src" / "backups", transport=t)
    blocks = [x for x in _levels(r, "datos") if x[0] == C.BLOCK]
    assert len(blocks) == 1 and "MÁS VIEJOS" in blocks[0][1]


def test_same_identity_from_another_host_blocks(tmp_path, clone):
    d, _ = backup(tmp_path)
    (d / "machine_id").write_text("equipo-a\n", encoding="utf-8")
    t = FakeReleases(tmp_path / "gh")
    _publish_meta(t, "equipo-a", "OTRO-PC", {"paper.duckdb": {"t": 1}})
    r = C.run(clone / "v2", d, tmp_path / "src" / "backups", transport=t)
    assert any("misma identidad" in x[1] for x in _levels(r, "datos") if x[0] == C.BLOCK)


def test_up_to_date_machine_is_not_blocked(tmp_path, clone):
    d, _ = backup(tmp_path)
    (d / "machine_id").write_text("equipo-a\n", encoding="utf-8")
    t = FakeReleases(tmp_path / "gh")
    _publish_meta(t, "equipo-a", platform.node(), {"paper.duckdb": {"t": 5, "u": 2}})
    _publish_meta(t, "equipo-b", "OTRO-PC", {"paper.duckdb": {"t": 9000}})   # otro equipo:
    r = C.run(clone / "v2", d, tmp_path / "src" / "backups", transport=t)  # no se compara
    assert r.level != C.BLOCK, _levels(r)
    assert sum("copia externa de" in x[1] for x in _levels(r, "copias")) == 2


def test_stale_compares_totals_per_db():
    assert datastate.stale_dbs({"p": {"a": 10, "b": 1}}, {"p": {"a": 9, "b": 2}}) == []
    assert datastate.stale_dbs({"p": {"a": 1}}, {"p": {"a": 9}, "q": {"x": 1}}) == [
        "p: 1 filas aquí < 9 en la copia publicada"]


def test_tasks_and_unpublished_code_are_reported(tmp_path, clone):
    (clone / "v2" / "nuevo.py").write_text("y = 2\n", encoding="utf-8")
    r = C.run(clone / "v2", tmp_path / "vacio", tmp_path / "bk", network=False)
    texts = [t for _, t in _levels(r, "tareas")]
    assert any("1 hechas · 1 en curso (T02) · 1 pendientes" in t for t in texts)
    assert any("solo en este equipo" in t for lvl, t in _levels(r, "código") if lvl == C.WARN)
