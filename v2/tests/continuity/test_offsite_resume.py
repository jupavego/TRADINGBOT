"""T127: la copia externa cortada a mitad retoma desde su última parte subida, sin repetir la
subida; reintenta una parte que falla una vez y nunca da por buena una copia a medias."""

import pytest

from eim.continuity import offsite as O
from eim.continuity import publish
from eim.data import backup as B
from eim.data.share_git import available
from tests.continuity.helpers import FakeReleases, backup, repo
from tests.data.backup_helpers import data

PART = 4096


class Flaky(FakeReleases):
    """Falla las llamadas a `upload` con esos números de orden (1, 2, …)."""

    def __init__(self, root, fail_on=()):
        super().__init__(root)
        self.fail_on, self.calls = set(fail_on), 0

    def upload(self, path):
        self.calls += 1
        if self.calls in self.fail_on:
            raise O.OffsiteError(f"corte simulado en {path.name}")
        super().upload(path)


def _extras(tmp_path, name):
    ex = tmp_path / f"extras-{name}"
    ex.mkdir()
    (ex / f"{name}.txt").write_text(name, encoding="utf-8")
    return ex


def _cut_after(n_parts):            # sube n partes y la siguiente falla en los 3 intentos
    return {n_parts + 1, n_parts + 2, n_parts + 3}


def test_a_cut_upload_resumes_from_the_last_part(tmp_path):
    _, bk = backup(tmp_path)
    work, sleeps = tmp_path / "bk" / ".continuity", []
    t = Flaky(tmp_path / "gh", _cut_after(2))
    with pytest.raises(O.OffsiteError, match="corte simulado"):
        O.push(t, bk, "a", work=work, part_bytes=PART, sleep=sleeps.append)
    assert sleeps == [20.0, 60.0] and O.remote_copies(t) == []      # a medias: no existe
    [pack_dir] = work.glob("pack-a__*")
    first = list(t.uploads)
    assert len(first) == 2 and (pack_dir / "pack.json").exists()
    ok = FakeReleases(tmp_path / "gh")                                # el día siguiente
    meta = O.push(ok, bk, "a", work=work, part_bytes=PART)
    names = [p["name"] for p in meta["parts"]]
    assert len(names) >= 3 and meta["resumed_parts"] == 2
    assert ok.uploads == names[2:] + [f"a__{bk.name}.meta.json"]      # sin repetir las dos
    [c] = O.remote_copies(ok)
    assert c.complete and B.verify(O.pull(ok, c, tmp_path / "dest")) == []
    assert not pack_dir.exists()                                      # punto de control cerrado


def test_a_part_that_fails_once_is_retried_in_the_same_run(tmp_path):
    _, bk = backup(tmp_path)
    sleeps = []
    t = Flaky(tmp_path / "gh", {2})
    meta = O.push(t, bk, "a", work=tmp_path / "w", part_bytes=PART, sleep=sleeps.append)
    assert sleeps == [20.0] and t.calls == len(meta["parts"]) + 2   # + el meta + el reintento
    assert O.remote_copies(t)[0].complete


def test_the_resumed_copy_keeps_the_extras_of_the_first_attempt(tmp_path):
    _, bk = backup(tmp_path)
    work = tmp_path / "w"
    with pytest.raises(O.OffsiteError):
        O.push(Flaky(tmp_path / "gh", _cut_after(1)), bk, "a", work=work,
               extras=_extras(tmp_path, "primero"), part_bytes=PART, sleep=lambda s: None)
    meta = O.push(FakeReleases(tmp_path / "gh"), bk, "a", work=work,
                  extras=_extras(tmp_path, "segundo"), part_bytes=PART)
    assert meta["extras"] == ["primero.txt"]       # el zip ya subido es el del primer intento
    t = FakeReleases(tmp_path / "gh")
    out = O.pull(t, O.remote_copies(t)[0], tmp_path / "dest")
    assert (out.parent / f"{bk.name}.extras" / "primero.txt").exists()


def test_a_part_lost_remotely_or_a_damaged_pack_is_uploaded_again(tmp_path):
    _, bk = backup(tmp_path)
    work = tmp_path / "w"
    with pytest.raises(O.OffsiteError):
        O.push(Flaky(tmp_path / "gh", _cut_after(2)), bk, "a", work=work, part_bytes=PART,
               sleep=lambda s: None)
    ok = FakeReleases(tmp_path / "gh")
    lost = sorted(p.name for p in (tmp_path / "gh").iterdir())[0]
    ok.delete(lost)                                       # desapareció de GitHub
    meta = O.push(ok, bk, "a", work=work, part_bytes=PART)
    assert meta["resumed_parts"] == 1 and lost in ok.uploads
    # empaquetado dañado (una parte truncada): se rehace y se sube entero
    _, bk2 = backup(tmp_path, n=1)
    with pytest.raises(O.OffsiteError):
        O.push(Flaky(tmp_path / "gh2", _cut_after(2)), bk2, "a", work=work, part_bytes=PART,
               sleep=lambda s: None)
    [pack_dir] = work.glob("pack-a__*")
    next(pack_dir.glob("*.zip.000")).write_bytes(b"x")
    ok2 = FakeReleases(tmp_path / "gh2")
    meta2 = O.push(ok2, bk2, "a", work=work, part_bytes=PART)
    assert meta2["resumed_parts"] == 0 and len(ok2.uploads) == len(meta2["parts"]) + 1


def test_leftovers_of_older_copies_are_cleaned(tmp_path):
    _, bk = backup(tmp_path)
    work = tmp_path / "w"
    for junk in ("pack-a__eim_20260101-000000", ".offsite-abc", "pack-b__eim_20260101-000000"):
        (work / junk).mkdir(parents=True)
    O.push(FakeReleases(tmp_path / "gh"), bk, "a", work=work, part_bytes=PART)
    assert sorted(p.name for p in work.iterdir()) == ["pack-b__eim_20260101-000000"]  # de otro


@pytest.mark.skipif(not available(), reason="git no disponible")
def test_publish_says_the_upload_was_resumed(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "RETRY_WAIT_S", (0.0,))
    clone, _ = repo(tmp_path)
    d = data(tmp_path)
    (d / "machine_id").write_text("equipo-a\n", encoding="utf-8")
    kw = {"repo": "prueba/datos", "machine": "equipo-a", "api": "http://127.0.0.1:9",
          "share": False, "home": tmp_path / "home"}
    r1 = publish.publish(clone / "v2", d, tmp_path / "bk", transport=Flaky(
        tmp_path / "gh", {2, 3, 4}), **kw)                 # sube la parte; el meta falla
    assert not r1["ok"]
    r2 = publish.publish(clone / "v2", d, tmp_path / "bk", transport=FakeReleases(
        tmp_path / "gh"), **kw)
    assert r2["ok"], r2["steps"]
    assert "(retomada: 1 ya subidas)" in r2["steps"][2]["text"]
