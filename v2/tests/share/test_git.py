"""T61: transporte por git (repo privado) probado con un remoto local `--bare`, sin red."""

import subprocess

import pytest

from eim.data import share
from eim.data.share_auto import ShareAgent, make_agent, save_config
from eim.data.share_git import GitError, GitTransport, available
from tests.share.helpers import M15, T0, build, rows
from tests.share.test_auto import Clock, machine

pytestmark = pytest.mark.skipif(not available(), reason="git no disponible")


@pytest.fixture
def remote(tmp_path):
    r = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(r)], check=True)
    return r.as_posix()


def _agents(d, name, remote, tmp_path, clock, ps, rs):
    from eim.data.share_auto import Live
    t = GitTransport(remote, d / "share_repo", name)
    return ShareAgent("api", d, t.view, name, {"reports.duckdb": Live(*rs.connection),
                                               "paper.duckdb": Live(*ps.connection)},
                      clock=clock, transport=t, backup_dir=tmp_path / name / "bk")


def test_two_machines_through_git(tmp_path, remote):
    a = build(tmp_path, "a", asofs=[T0 + i * M15 for i in range(1, 4)])
    b = build(tmp_path, "b", asofs=[T0 + i * M15 for i in range(3, 7)])
    clock = Clock()
    with machine(b, tmp_path / "unused", "b", clock) as (psb, rsb, _, _, _), \
            machine(a, tmp_path / "unused2", "a", clock) as (psa, rsa, _, _, _):
        ag_b = _agents(b, "b", remote, tmp_path, clock, psb, rsb)
        ag_a = _agents(a, "a", remote, tmp_path, clock, psa, rsa)
        ag_b.tick()                                   # b publica su rama machine/b
        assert ag_b.error == "", ag_b.error
        heads = ag_b.transport.remote_heads()
        assert set(heads) == {"b"}
        ag_a.tick()                                   # a trae b, lo une y publica machine/a
        assert ag_a.error == "", ag_a.error
        assert len(psa.execute("SELECT * FROM paper_ctx")) == 6
        assert set(ag_a.transport.remote_heads()) == {"a", "b"}
        clock.t += 7200                               # b trae lo de a (ya con la unión)
        ag_b.next_import = ag_b.next_export = 0
        ag_b.tick()
        assert ag_b.error == "" and len(psb.execute("SELECT * FROM paper_ctx")) == 6
        # nada nuevo: ni importa ni vuelve a publicar
        before = ag_b.transport.remote_heads()
        clock.t += 7200
        ag_b.next_import = ag_b.next_export = 0
        ag_b.tick()
        assert ag_b.transport.remote_heads() == before
    # la historia del servidor no crece: una sola confirmación por rama
    log = subprocess.run(["git", "--git-dir", remote, "rev-list", "--count", "machine/b"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert log == "1"


def test_push_rewrites_single_root_commit_and_skips_when_unchanged(tmp_path, remote):
    t = GitTransport(remote, tmp_path / "w", "m1")
    t.pull()
    (t.own / "20261001T000000Z-api").mkdir()
    (t.own / "20261001T000000Z-api" / "manifest.json").write_text("{}", encoding="utf-8")
    (t.own / ".20261001T000001Z-api.partial").mkdir()          # a medias: no se publica
    (t.own / ".20261001T000001Z-api.partial" / "x.parquet").write_bytes(b"x")
    assert t.push() is True and t.push() is False
    (t.own / "20261002T000000Z-api").mkdir()
    (t.own / "20261002T000000Z-api" / "manifest.json").write_text("{}", encoding="utf-8")
    assert t.push() is True
    files = subprocess.run(["git", "--git-dir", remote, "ls-tree", "-r", "--name-only",
                            "machine/m1"], capture_output=True, text=True).stdout
    assert "20261002T000000Z-api/manifest.json" in files and "partial" not in files
    count = subprocess.run(["git", "--git-dir", remote, "rev-list", "--count", "machine/m1"],
                           capture_output=True, text=True).stdout.strip()
    assert count == "1"


def test_reinstalled_machine_recovers_its_branch(tmp_path, remote):
    t = GitTransport(remote, tmp_path / "w1", "m1")
    t.pull()
    (t.own / "20261001T000000Z-api").mkdir()
    (t.own / "20261001T000000Z-api" / "manifest.json").write_text("{}", encoding="utf-8")
    t.push()
    again = GitTransport(remote, tmp_path / "w2", "m1")      # equipo nuevo, mismo alias
    again.pull()
    assert (again.own / "20261001T000000Z-api" / "manifest.json").exists()


def test_git_errors_are_reported(tmp_path):
    t = GitTransport((tmp_path / "no_hay.git").as_posix(), tmp_path / "w", "m1", timeout=20)
    with pytest.raises(GitError):
        t.pull()


def test_oversize_file_refused(tmp_path, remote, monkeypatch):
    import eim.data.share_git as g
    monkeypatch.setattr(g, "MAX_FILE", 10)
    t = GitTransport(remote, tmp_path / "w", "m1")
    t.pull()
    (t.own / "big.parquet").write_bytes(b"x" * 100)
    with pytest.raises(GitError, match="90 MB"):
        t.push()


def test_config_and_cli_git_mode(tmp_path, remote, capsys, monkeypatch):
    monkeypatch.delenv("EIM_MACHINE", raising=False)
    monkeypatch.delenv("EIM_SHARED_DIR", raising=False)
    d = tmp_path / "data"
    assert share.main(["setup", "--data-dir", str(d), "--git-url", remote,
                       "--machine", "pc-git"]) == 0
    assert "repo privado" in capsys.readouterr().out
    ag = make_agent("api", d, {}, env={})
    assert ag.transport is not None and ag.machine == "pc-git" and ag.shared_dir.name == "view"
    assert share.main(["setup", "--data-dir", str(d)]) == 1            # sin destino: error claro
    # CLI manual en modo git: exporta y publica
    b = build(tmp_path, "pc-git", asofs=[T0 + M15])
    save_config(b, None, "pc-git", remote)
    assert share.main(["export", "--data-dir", str(b), "--api", "http://127.0.0.1:1"]) == 0
    assert "git: publicado" in capsys.readouterr().out
    assert rows(b, "paper.duckdb", "SELECT count(*) FROM paper_ctx") == [(1,)]
