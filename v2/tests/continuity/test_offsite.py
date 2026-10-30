"""T125: copia externa — ida y vuelta íntegra, idempotente, partes dañadas, subidas a medias y
poda que solo toca lo propio."""

import json
import zipfile

import pytest

from eim.continuity import offsite as O
from eim.data import backup as B
from tests.continuity.helpers import FakeReleases, backup
from tests.data.backup_helpers import content, manifest


def _extras(tmp_path):
    ex = tmp_path / "extras"
    (ex / "git").mkdir(parents=True)
    (ex / "git" / "estado.txt").write_text("rama main\n", encoding="utf-8")
    return ex


def test_roundtrip_is_identical(tmp_path):
    d, bk = backup(tmp_path)
    t = FakeReleases(tmp_path / "gh")
    meta = O.push(t, bk, "equipo-a", extras=_extras(tmp_path), info={"host": "PC-A"},
                  part_bytes=4096)
    assert not meta["skipped"] and len(meta["parts"]) > 1          # troceada
    assert t.uploads[-1] == f"equipo-a__{bk.name}.meta.json"     # el meta, lo último
    [c] = O.remote_copies(t)
    assert c.complete and c.machine == "equipo-a" and c.meta["host"] == "PC-A"
    assert c.rows == {db: v["tables"] for db, v in manifest(bk)["dbs"].items()}
    out = O.pull(t, c, tmp_path / "otro_equipo" / "backups")
    assert out == tmp_path / "otro_equipo" / "backups" / "remote" / "equipo-a" / bk.name
    assert B.verify(out) == []
    for db in (B.DB_NAME, B.PAPER, B.LEADERS):
        assert content(out / db) == content(d / db)
    assert (out.parent / f"{bk.name}.extras" / "git" / "estado.txt").exists()
    assert not list(out.parent.glob(".*.partial"))
    assert O.pull(t, c, tmp_path / "otro_equipo" / "backups") == out   # repetir: ya está


def test_push_twice_uploads_nothing_new(tmp_path):
    _, bk = backup(tmp_path)
    t = FakeReleases(tmp_path / "gh")
    O.push(t, bk, "a", part_bytes=4096, work=tmp_path / "w" / "no-existe")   # la crea
    n = len(t.uploads)
    assert O.push(t, bk, "a", part_bytes=4096)["skipped"]
    assert len(t.uploads) == n


def test_interrupted_upload_is_never_complete_and_resumes(tmp_path):
    _, bk = backup(tmp_path)
    t = FakeReleases(tmp_path / "gh")
    meta = O.push(t, bk, "a", part_bytes=4096)
    t.delete(f"a__{bk.name}.meta.json")            # se cortó antes del meta
    t.delete(meta["parts"][-1]["name"])            # y faltaba la última parte
    assert O.remote_copies(t) == []
    t.uploads.clear()
    O.push(t, bk, "a", part_bytes=4096)
    assert t.uploads[-1] == f"a__{bk.name}.meta.json" and len(t.uploads) == len(meta["parts"]) + 1
    [c] = O.remote_copies(t)
    assert c.complete and B.verify(O.pull(t, c, tmp_path / "dest")) == []


def test_missing_part_makes_copy_incomplete(tmp_path):
    _, bk = backup(tmp_path)
    t = FakeReleases(tmp_path / "gh")
    meta = O.push(t, bk, "a", part_bytes=4096)
    t.delete(meta["parts"][0]["name"])
    [c] = O.remote_copies(t)
    assert not c.complete and c.missing == [meta["parts"][0]["name"]]
    with pytest.raises(O.OffsiteError, match="incompleta"):
        O.pull(t, c, tmp_path / "dest")


def test_damaged_part_is_rejected_and_nothing_is_left(tmp_path):
    _, bk = backup(tmp_path)
    t = FakeReleases(tmp_path / "gh")
    meta = O.push(t, bk, "a", part_bytes=4096)
    p = t.root / meta["parts"][0]["name"]
    raw = bytearray(p.read_bytes())
    raw[100] ^= 0xFF                                # mismo tamaño, contenido distinto
    p.write_bytes(bytes(raw))
    [c] = O.remote_copies(t)
    with pytest.raises(O.OffsiteError, match="dañada"):
        O.pull(t, c, tmp_path / "dest")
    assert not (tmp_path / "dest" / "remote" / "a" / bk.name).exists()
    assert not list((tmp_path / "dest" / "remote" / "a").glob(".*"))


def test_damaged_local_copy_never_leaves(tmp_path):
    _, bk = backup(tmp_path)
    (bk / B.PAPER).write_bytes(b"roto")
    with pytest.raises(O.OffsiteError, match="no es una copia íntegra"):
        O.push(FakeReleases(tmp_path / "gh"), bk, "a")


def test_prune_keeps_latest_own_and_never_touches_others(tmp_path):
    t = FakeReleases(tmp_path / "gh")
    names = []
    for i in range(3):
        _, bk = backup(tmp_path, n=i)
        O.push(t, bk, "a", part_bytes=4096)
        names.append(bk.name)
    _, other = backup(tmp_path, sub="b")
    O.push(t, other, "b", part_bytes=4096)
    orphan = tmp_path / "a__eim_x.zip.000"         # subida abandonada hace mucho
    orphan.write_bytes(b"medio")
    t.upload(orphan)
    t.created["a__eim_x.zip.000"] = "2000-01-01T00:00:00Z"
    gone = O.prune(t, "a", keep=2)
    assert f"a__{names[0]}.meta.json" in gone and "a__eim_x.zip.000" in gone
    left = [(c.machine, c.backup) for c in O.remote_copies(t)]
    assert left == [("a", names[1]), ("a", names[2]), ("b", other.name)]
    assert not any(n.startswith(f"a__{names[0]}") for n in t.assets())


def test_zip_with_paths_outside_is_rejected(tmp_path):
    z = tmp_path / "malo.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../fuera.txt", "x")
    with zipfile.ZipFile(z) as f, pytest.raises(O.OffsiteError, match="no permitida"):
        O._safe_extract(f, tmp_path / "dest")


def test_meta_records_rows_and_commit(tmp_path):
    _, bk = backup(tmp_path)
    t = FakeReleases(tmp_path / "gh")
    O.push(t, bk, "a")
    meta = json.loads((t.root / f"a__{bk.name}.meta.json").read_text(encoding="utf-8"))
    assert meta["format"] == O.FORMAT and meta["backup"] == bk.name
    assert meta["dbs"][B.PAPER]["tables"] == {"t": 5, "u": 2}
    assert meta["zip_sha256"] and meta["backup_bytes"] > 0
