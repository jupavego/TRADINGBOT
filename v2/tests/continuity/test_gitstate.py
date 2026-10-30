"""T125: estado del código frente al remoto — atraso, trabajo sin confirmar, commits sin subir
y worktrees; solo lectura."""

import subprocess

from eim.continuity import gitstate as G
from tests.continuity.helpers import repo, run


def test_clean_clone_has_nothing_unpublished(tmp_path):
    clone, _ = repo(tmp_path)
    s = G.state(clone)
    assert s.fetched and s.branch == "main" and s.behind_main == 0 and s.unpublished == []


def test_reports_behind_dirty_local_commits_and_worktrees(tmp_path):
    clone, origin = repo(tmp_path)
    other = tmp_path / "otro_equipo"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    (other / "v2" / "y.py").write_text("y = 1\n", encoding="utf-8")
    run("add", "-A", cwd=other)
    run("commit", "-q", "-m", "desde otro equipo", cwd=other)
    run("push", "-q", "origin", "main", cwd=other)
    run("checkout", "-q", "-b", "trabajo", cwd=clone)
    (clone / "v2" / "x.py").write_text("x = 2\n", encoding="utf-8")
    run("commit", "-qam", "solo aquí", cwd=clone)
    (clone / "v2" / "x.py").write_text("x = 3\n", encoding="utf-8")
    wt = tmp_path / "wt"
    run("worktree", "add", "-q", "-b", "otra", str(wt), "main", cwd=clone)
    (wt / "PLAN" / "nota.md").write_text("a medias\n", encoding="utf-8")
    head = run("rev-parse", "HEAD", cwd=clone)
    s = G.state(clone)
    assert s.behind_main == 1 and s.ahead_main == 1
    assert s.local_only_branches == {"trabajo": 1}
    dirty = {w.branch: w.dirty for w in s.worktrees}
    assert dirty["trabajo"] == ["v2/x.py"] and dirty["otra"] == ["PLAN/nota.md"]
    assert len(s.unpublished) == 3
    assert run("rev-parse", "HEAD", cwd=clone) == head                # no movió nada
    assert (clone / "v2" / "x.py").read_text(encoding="utf-8") == "x = 3\n"
    assert G.main_root(wt) == clone


def test_failed_fetch_is_reported_not_raised(tmp_path):
    clone, _ = repo(tmp_path)
    run("remote", "set-url", "origin", str(tmp_path / "no-existe.git"), cwd=clone)
    s = G.state(clone)
    assert not s.fetched and s.fetch_error
