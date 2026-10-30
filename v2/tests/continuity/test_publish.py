"""T125: publicar — copia → copia externa (con extras) → experiencia desde la copia, sin tocar
la carpeta viva y sin duplicar al repetir; el lanzador no opera sin historial."""

import json
import subprocess

import pytest

from eim.continuity import extras, offsite, publish
from eim.data import backup as B
from eim.data import share
from eim.data.share_git import available
from eim.operation import __main__ as op_main
from tests.continuity.helpers import FakeReleases, repo, run
from tests.data.backup_helpers import data
from tests.share.helpers import M15, T0, build

pytestmark = pytest.mark.skipif(not available(), reason="git no disponible")


def _home(tmp_path, clone):
    mem = tmp_path / "home" / ".claude" / "projects" / extras.claude_slug(clone) / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("- nota\n", encoding="utf-8")
    return tmp_path / "home"


def test_publish_twice_is_idempotent_and_logged(tmp_path):
    clone, _ = repo(tmp_path)
    (clone / "v2" / "x.py").write_text("x = 9\n", encoding="utf-8")      # trabajo a medias
    d = data(tmp_path)
    (d / "machine_id").write_text("equipo-a\n", encoding="utf-8")
    t = FakeReleases(tmp_path / "gh")
    kw = {"repo": "prueba/datos", "machine": "equipo-a", "api": "http://127.0.0.1:9",
          "share": False, "transport": t, "home": _home(tmp_path, clone)}
    r1 = publish.publish(clone / "v2", d, tmp_path / "bk", **kw)
    assert r1["ok"], r1["steps"]
    steps = {s["step"]: s["text"] for s in r1["steps"]}
    assert "(nueva)" in steps["copia local"] and "PENDIENTE de subir" in steps["código"]
    [c] = offsite.remote_copies(t)
    assert "git/clon.patch" in c.meta["extras"] and any(
        e.endswith("memory/MEMORY.md") for e in c.meta["extras"])
    assert "data/machine_id" in c.meta["extras"]
    r2 = publish.publish(clone / "v2", d, tmp_path / "bk", **kw)
    assert "(la de hoy)" in r2["steps"][0]["text"] and "(ya estaba)" in r2["steps"][2]["text"]
    assert len(offsite.remote_copies(t)) == 1
    log = (d / "continuity" / "publish.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["ok"] for x in log] == [True, True]
    out = offsite.pull(t, c, tmp_path / "nuevo" / "backups")         # el parche se aplica
    patch = out.parent / f"{c.backup}.extras" / "git" / "clon.patch"
    run("checkout", "-q", "--", "v2/x.py", cwd=clone)
    run("apply", str(patch), cwd=clone)
    assert (clone / "v2" / "x.py").read_text(encoding="utf-8") == "x = 9\n"


def test_share_from_copy_leaves_copy_intact_and_others_can_import(tmp_path):
    remote = tmp_path / "datos.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    a = build(tmp_path, "a", asofs=[T0 + i * M15 for i in range(1, 4)])
    bk = B.create(a, tmp_path / "bk", keep=0)
    text = publish.share_from_copy(bk, tmp_path / "bk", remote.as_posix(), "a")
    assert "publicada" in text and B.verify(bk) == []
    again = publish.share_from_copy(bk, tmp_path / "bk", remote.as_posix(), "a")
    assert "ya hecha" in again and "sin cambios" in again
    c = build(tmp_path, "c")
    share.main(["setup", "--data-dir", str(c), "--git-url", remote.as_posix()])
    assert share.main(["import", "--data-dir", str(c), "--apply",
                       "--backup-dir", str(tmp_path / "bk_c")]) == 0
    from tests.share.helpers import rows
    assert rows(c, "paper.duckdb", "SELECT count(*) FROM paper_ctx") == [(3,)]


def test_share_is_skipped_when_auto_mode_owns_the_branch(tmp_path):
    clone, _ = repo(tmp_path)
    d = data(tmp_path)
    (d / "share_config.json").write_text("{}", encoding="utf-8")
    r = publish.publish(clone / "v2", d, tmp_path / "bk", repo="prueba/datos", machine="a",
                        api="http://127.0.0.1:9", transport=FakeReleases(tmp_path / "gh"),
                        home=tmp_path / "h")
    assert "modo automático" in {s["step"]: s["text"] for s in r["steps"]}["experiencia"]


def test_operation_refuses_empty_data(tmp_path, monkeypatch, capsys):
    started = []
    monkeypatch.setattr(op_main, "Watchdog", lambda *a, **k: started.append(a) or _NoRun())
    assert op_main.main(["run", "--data-dir", str(tmp_path / "vacio")]) == 3
    assert "NO SE ARRANCA" in capsys.readouterr().err and started == []
    assert not (tmp_path / "vacio" / "reports.duckdb").exists()
    assert op_main.main(["run", "--data-dir", str(tmp_path / "vacio"),
                         "--allow-empty-data"]) == 0
    d = data(tmp_path)
    assert op_main.main(["run", "--data-dir", str(d)]) == 0 and len(started) == 2


class _NoRun:
    def run(self):
        return None
