"""Ejecutor aislado (modo B): sin claves, acotado en tiempo y recursos, versión fijada."""

import json
import os
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from eim.data.bots.runner import (
    Limits,
    RunSpec,
    can_unshare_net,
    checkout_state,
    clean_env,
    run_isolated,
)

POSIX = os.name != "nt"


def bot(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "bot.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return script


def spec(script: Path, **kw) -> RunSpec:
    return RunSpec(python=Path(sys.executable), script=script, **kw)


ECHO = """
    import json, os
    from pathlib import Path
    req = json.loads(Path("request.json").read_text())
    Path("out.json").write_text(json.dumps({"echo": req, "env": dict(os.environ),
        "files": sorted(p.name for p in Path(".").iterdir()), "cwd": os.getcwd()}))
"""


def test_runs_and_returns_the_bot_output(tmp_path):
    res = run_isolated(spec(bot(tmp_path, ECHO), request={"a": 1}, files={"candles.json": "[]"}))
    assert res.status == "ok" and res.output["echo"] == {"a": 1}
    assert res.output["files"] == ["candles.json", "request.json"]
    assert not Path(res.output["cwd"]).exists()          # el directorio de trabajo se borró


def test_subprocess_receives_no_credentials(tmp_path, monkeypatch):
    secrets = {"EIM_TESTNET_API_KEY": "k-123", "EIM_TESTNET_API_SECRET": "s-456",
               "BINANCE_SECRET": "s-789", "MY_TOKEN": "t-000", "AWS_ACCESS_KEY_ID": "a-111",
               "GITHUB_PASSWORD": "p-222", "EIM_API_TOKEN": "t-333", "SOME_COOKIE": "c-444"}
    for k, v in secrets.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("UNRELATED_VAR", "no-debe-pasar")
    res = run_isolated(spec(bot(tmp_path, ECHO)))
    env = res.output["env"]
    assert not set(secrets) & set(env)
    assert not any(v in json.dumps(env) for v in secrets.values())
    assert "UNRELATED_VAR" not in env                   # lista blanca, no lista negra
    assert env["HTTPS_PROXY"].startswith("http://127.0.0.1:9") and env["PIP_NO_INDEX"] == "1"
    assert env["HOME"] == res.output["cwd"]             # sin ~/.config ni claves guardadas


def test_workdir_has_no_config_or_key_files(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("EIM_TESTNET_API_KEY=zzz")     # junto al bot: no se copia
    monkeypatch.chdir(tmp_path)
    res = run_isolated(spec(bot(tmp_path, ECHO)))
    assert ".env" not in res.output["files"]


def test_extra_env_with_secret_looking_name_is_refused(tmp_path):
    with pytest.raises(ValueError):
        clean_env(tmp_path, {"EXCHANGE_API_KEY": "x"})
    res = run_isolated(spec(bot(tmp_path, ECHO), extra_env={"FOO_SECRET": "x"}))
    assert res.status == "degraded" and "secreto" in res.warnings[0]
    ok = run_isolated(spec(bot(tmp_path, ECHO), extra_env={"BOT_MODE": "signal"}))
    assert ok.output["env"]["BOT_MODE"] == "signal"


@pytest.mark.perf
def test_timeout_kills_the_bot_and_is_degraded_not_an_exception(tmp_path):
    script = bot(tmp_path, "import time\ntime.sleep(60)\n")
    res = run_isolated(spec(script, limits=Limits(timeout_s=1.0)))
    assert res.status == "degraded" and "excedió" in res.warnings[0]
    assert res.duration_s < 20, f"timeout de 1 s y el bot vivió {res.duration_s:.1f} s"


@pytest.mark.skipif(not POSIX, reason="el grupo de procesos solo existe en POSIX")
def test_timeout_also_kills_children(tmp_path):
    pidfile = tmp_path / "child.pid"
    script = bot(tmp_path, f"""
        import subprocess, sys, time
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        open({str(pidfile)!r}, "w").write(str(p.pid))
        time.sleep(60)
    """)
    run_isolated(spec(script, limits=Limits(timeout_s=1.5)))
    pid = int(pidfile.read_text())
    import time
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail("el proceso hijo del bot sigue vivo")


@pytest.mark.parametrize("body,fragment", [
    ("raise RuntimeError('boom')", "código"),
    ("import sys; sys.exit(3)", "código 3"),
    ("pass", "no escribió out.json"),
    ("open('out.json','w').write('{no json')", "JSON"),
    ("open('out.json','w').write('[1, 2]')", "objeto"),
    ("import os, signal; os.kill(os.getpid(), signal.SIGKILL)" if POSIX else "pass", ""),
])
def test_crashes_and_bad_output_are_degraded_without_exception(tmp_path, body, fragment):
    res = run_isolated(spec(bot(tmp_path, body)))
    assert res.status == "degraded" and res.output is None
    assert fragment in res.warnings[0]


def test_oversized_output_is_rejected(tmp_path):
    script = bot(tmp_path, "open('out.json','w').write('{\"x\": \"' + 'a' * 5000 + '\"}')")
    res = run_isolated(spec(script, limits=Limits(max_output_bytes=1000)))
    assert res.status == "degraded"


@pytest.mark.skipif(not POSIX, reason="rlimit solo en POSIX")
def test_memory_is_bounded(tmp_path):
    script = bot(tmp_path, "x = bytearray(1500 * 1024 * 1024)\nopen('out.json','w').write('{}')")
    res = run_isolated(spec(script, limits=Limits(memory_mb=300, timeout_s=30)))
    assert res.status == "degraded"


def test_missing_interpreter_or_script_is_degraded(tmp_path):
    res = run_isolated(RunSpec(python=tmp_path / "nope", script=tmp_path / "nada.py"))
    assert res.status == "degraded"
    bad = run_isolated(spec(bot(tmp_path, ECHO), files={"../escape.txt": "x"}))
    assert bad.status == "degraded" and "no permitido" in bad.warnings[0]


@pytest.mark.skipif(not can_unshare_net(), reason="el sistema no permite `unshare --net`")
def test_network_is_cut_when_the_system_allows_it(tmp_path):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    script = bot(tmp_path, f"""
        import json, socket
        try:
            socket.create_connection(("127.0.0.1", {port}), timeout=2).close()
            reached = True
        except OSError:
            reached = False
        open("out.json", "w").write(json.dumps({{"reached": reached}}))
    """)
    try:
        res = run_isolated(spec(script))
    finally:
        srv.close()
    assert res.status == "ok" and res.network_isolated and res.output == {"reached": False}


def test_network_isolation_can_be_disabled_and_is_reported(tmp_path):
    res = run_isolated(spec(bot(tmp_path, ECHO), isolate_network=False))
    assert res.status == "ok" and res.network_isolated is False


# --- versión fijada por SHA -----------------------------------------------------------------
def git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "botrepo"
    r.mkdir()
    git(r, "init", "-q")
    (r / "strategy.py").write_text("x = 1\n")
    git(r, "add", ".")
    git(r, "commit", "-qm", "init")
    return r


def test_pinned_sha_must_match_and_checkout_must_be_clean(tmp_path, repo):
    sha = git(repo, "rev-parse", "HEAD")
    script = bot(tmp_path, ECHO)
    assert checkout_state(repo) == (sha, False)
    assert run_isolated(spec(script, bot_dir=repo, expected_sha=sha)).status == "ok"
    wrong = run_isolated(spec(script, bot_dir=repo, expected_sha="0" * 40))
    assert wrong.status == "degraded" and "distinta de la fijada" in wrong.warnings[0]
    (repo / "strategy.py").write_text("x = 2  # modificado\n")
    dirty = run_isolated(spec(script, bot_dir=repo, expected_sha=sha))
    assert dirty.status == "degraded" and "cambios locales" in dirty.warnings[0]
    git(repo, "checkout", "-q", "strategy.py")
    (repo / "nuevo.py").write_text("import os  # archivo sin versionar que sombrea al bot\n")
    untracked = run_isolated(spec(script, bot_dir=repo, expected_sha=sha))
    assert untracked.status == "degraded" and "cambios locales" in untracked.warnings[0]
    (repo / "nuevo.py").unlink()
    (repo / "strategy.py").write_text("x = 3\n")
    git(repo, "commit", "-qam", "otro")
    moved = run_isolated(spec(script, bot_dir=repo, expected_sha=sha))
    assert moved.status == "degraded" and "distinta de la fijada" in moved.warnings[0]


def test_not_a_git_checkout_fails_closed(tmp_path):
    res = run_isolated(spec(bot(tmp_path, ECHO), bot_dir=tmp_path, expected_sha="a" * 40))
    assert res.status == "degraded"
