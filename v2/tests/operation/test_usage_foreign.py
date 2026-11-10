"""T141: qué son los programas ajenos que cargan el equipo. Sus órdenes no salen de `data/usage`."""

import json
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from eim.operation import usage, usage_foreign, usage_summary
from eim.operation.usage_foreign import Identifier, clean_command, clean_dir, trees
from eim.operation.usage_win import FILETIME_UNIX_S, Proc

MB = 1 << 20
T0 = 1_793_600_000.0                      # 2026-11-02 06:13:20 UTC


def ft(unix_s: float) -> int:
    return int((unix_s + FILETIME_UNIX_S) * 1e7)


def proc(pid, ppid, name="python.exe", born=T0 - 3600, cpu=0, ram=50 * MB, commit=200 * MB, prio=8):
    return Proc(pid, ppid, name, 1, prio, ft(born), cpu, ram, commit)


def by_cpu(values):
    return lambda p: values.get(p.pid, 0.0)


@pytest.mark.parametrize("raw, want", [
    (r'"C:\Users\jo\venv\Scripts\python.exe" -I scripts\23_modelo.py --procesos 7',
     r"python.exe -I scripts\23_modelo.py --procesos 7"),
    ('python -I -c "import os; print(os.environ)" extra', "python -I -c …"),
    ("node -e \"require('x')\"", "node -e …"),
    ("python tool.py --token abc123 --api-key=zzz", "python tool.py --token ***  --api-key=***"),
    ('python tool.py --password "con espacios" --x 1', "python tool.py --password *** --x 1"),
    ("python get.py https://user:clave@host.tld/ruta?firma=abc&x=1 --y",
     "python get.py https://host.tld/ruta --y"),
    ("python run.py sk0123456789abcdef0123456789abcdef0123", "python run.py ***"),
    ("python tool.py --token:abc123 --x 1", "python tool.py --token:*** --x 1"),
    ("mysql -u yo -p hunter2 --x 1", "mysql -u yo -p *** --x 1"),
    ("python auth_check.py --procesos 7", "python auth_check.py --procesos 7"),
])
def test_clean_command_drops_paths_inline_code_and_secrets(raw, want):
    assert " ".join(clean_command(raw).split()) == " ".join(want.split())


def test_clean_command_and_dir_are_short_and_keep_what_identifies():
    long = "python.exe " + "x " * 200
    assert len(clean_command(long)) == usage_foreign.CMD_MAX and clean_command(long).endswith("…")
    assert clean_command(None) is None and clean_command("") is None
    assert clean_dir("C:\\a\\b\\") == "C:\\a\\b" and clean_dir(None) is None
    deep = "C:\\" + "carpeta\\" * 30 + "PROTOTIPO"
    assert len(clean_dir(deep)) == usage_foreign.CWD_MAX and clean_dir(deep).endswith("PROTOTIPO")


def test_trees_join_a_pool_that_no_worker_passes_alone():
    procs = {1: proc(1, 900, ram=20 * MB, commit=30 * MB)}
    for pid in range(2, 9):                                         # 7 trabajadores al 4 %
        procs[pid] = proc(pid, 1, born=T0 - 60, ram=100 * MB, commit=300 * MB)
    cpu = {pid: 4.0 for pid in range(2, 9)}
    t = trees(procs, {}, by_cpu(cpu))
    assert len(t) == 1 and t[0]["pid"] == 1 and t[0]["n"] == 8 and t[0]["cpu"] == 28.0
    assert t[0]["ram_mb"] == 720.0 and t[0]["commit_mb"] == 2130.0 and t[0]["prio"] == 8


def test_trees_keep_out_the_eim_small_programs_and_unnamed_apps():
    procs = {
        10: proc(10, 900, prio=6),                                  # del EIM
        11: proc(11, 10, born=T0 - 60, prio=6),                     # hijo del EIM, con su papel
        20: proc(20, 900),                                          # orden suelta: no llega
        30: proc(30, 900, "chrome.exe", ram=2000 * MB),             # su nombre ya dice qué es
        40: proc(40, 900, "blender.exe", ram=400 * MB, prio=4),     # por memoria, sin CPU
        50: proc(50, 900, cpu=1),                                   # justo por CPU
    }
    t = trees(procs, {10: "api", 11: "api"}, by_cpu({20: 1.0, 30: 90.0, 50: 5.0}))
    assert [x["pid"] for x in t] == [50, 40]
    assert t[1]["name"] == "blender.exe" and t[1]["prio"] == 4


def test_trees_stop_at_a_reused_pid_and_keep_the_top_ones():
    procs = {1: proc(1, 900, born=T0 - 10), 2: proc(2, 1, born=T0 - 500)}   # el 1 nació después
    cpu = {1: 10.0, 2: 20.0}
    assert [x["pid"] for x in trees(procs, {}, by_cpu(cpu))] == [2, 1]
    many = {pid: proc(pid, 900) for pid in range(100, 120)}
    t = trees(many, {}, by_cpu({pid: float(pid) for pid in many}))
    assert len(t) == usage_foreign.MAX_TREES and t[0]["pid"] == 119


def test_identifier_reads_each_process_once_and_forgets_the_dead():
    calls = []
    backend = SimpleNamespace(
        command_line=lambda pid: calls.append(pid) or f"python job{pid}.py --token x",
        working_dir=lambda pid: f"C:\\p{pid}\\")
    ident = Identifier(backend)
    procs = {1: proc(1, 900)}
    cpu = by_cpu({1: 50.0})
    first = ident.identify(procs, {}, cpu)
    assert first[0]["cmd"] == "python job1.py --token ***" and first[0]["cwd"] == "C:\\p1"
    assert ident.identify(procs, {}, cpu)[0]["cmd"] == first[0]["cmd"] and calls == [1]
    assert ident.identify({}, {}, cpu) == []                        # terminó: se olvida
    reborn = {1: proc(1, 900, born=T0 - 5)}                         # mismo PID, otro proceso
    assert ident.identify(reborn, {}, cpu)[0]["cmd"] and calls == [1, 1]


def test_a_failed_read_is_retried_but_a_good_one_is_not():
    answers = iter([None, "python tarde.py"])
    calls = []

    def command_line(pid):
        calls.append(pid)
        return next(answers)

    ident = Identifier(SimpleNamespace(command_line=command_line, working_dir=lambda pid: None))
    procs, cpu = {1: proc(1, 900)}, by_cpu({1: 50.0})
    assert ident.identify(procs, {}, cpu)[0]["cmd"] is None
    assert ident.identify(procs, {}, cpu)[0]["cmd"] == "python tarde.py"
    assert ident.identify(procs, {}, cpu)[0]["cmd"] == "python tarde.py" and len(calls) == 2


def test_python_under_node_is_its_own_tree():
    procs = {1: proc(1, 900, "node.exe"), 2: proc(2, 1, born=T0 - 60), 3: proc(3, 2, born=T0 - 50)}
    t = trees(procs, {}, by_cpu({2: 10.0, 3: 30.0}))
    assert [(x["pid"], x["name"], x["n"]) for x in t] == [(2, "python.exe", 2)]


def test_identifier_without_permission_leaves_it_unnamed_but_measured():
    def denied(pid):
        raise OSError("acceso denegado")

    ident = Identifier(SimpleNamespace(command_line=denied, working_dir=denied))
    t = ident.identify({1: proc(1, 900)}, {}, by_cpu({1: 50.0}))[0]
    assert t["cmd"] is None and t["cwd"] is None and t["cpu"] == 50.0


win_only = pytest.mark.skipif(sys.platform != "win32", reason="lectura de procesos de Windows")


@win_only
def test_windows_reads_the_command_line_and_folder_of_another_process(tmp_path):
    from eim.operation import usage_win

    script = tmp_path / "trabajo_pesado.py"
    script.write_text("import time\ntime.sleep(30)\n")
    child = subprocess.Popen([sys.executable, str(script), "--procesos", "7"], cwd=tmp_path)  # noqa: S603
    try:
        cmd = cwd = None
        for _ in range(100):                # justo al nacer aún no tiene bloque ni carpeta
            cmd = usage_win.command_line(child.pid)
            cwd = usage_win.working_dir(child.pid)
            if cmd and cwd:
                break
            time.sleep(0.05)
        assert "trabajo_pesado.py" in cmd and "--procesos 7" in cmd
        assert cwd.rstrip("\\").lower() == str(tmp_path).lower()
    finally:
        child.kill()
        child.wait()
    assert usage_win.command_line(4) is None                # System: sin permiso, sin excepción
    assert usage_win.working_dir(4) is None
    assert usage_win.command_line(0xFFFFFF0) is None        # no existe


@win_only
def test_windows_reports_hard_faults_in_the_snapshot():
    from eim.operation import usage_win

    assert any(p.faults > 0 for p in usage_win.snapshot().values())


def test_sampler_adds_the_foreign_programs_and_the_api_beat(tmp_path):
    hb = tmp_path / "operation" / "heartbeat.json"
    hb.parent.mkdir()
    hb.write_text(json.dumps({"last_heartbeat": int((T0 - 400) * 1000)}))
    p1 = proc(13, 1, cpu=0, ram=400 * MB)
    p2 = proc(13, 1, cpu=6 * 10**7, ram=400 * MB)
    steps = iter([({13: p1}, (0, 0)), ({13: p2}, (3 * 10**8, 12 * 10**8))])
    state = {}

    def snapshot():
        state["cur"] = next(steps)
        return state["cur"][0]

    backend = SimpleNamespace(snapshot=snapshot, system_times=lambda: state["cur"][1],
                              memory=lambda: {"ram_free_mb": 5000}, listeners=lambda ports: {},
                              command_line=lambda pid: "python a.py",
                              working_dir=lambda pid: "C:\\p")
    s = usage.Sampler(tmp_path, backend=backend, ncpu=4)
    assert s.sample(T0 - 30) is None
    rec = s.sample(T0)
    assert rec["foreign"][0]["cmd"] == "python a.py" and rec["foreign"][0]["cwd"] == "C:\\p"
    assert rec["foreign"][0]["cpu"] == 5.0 and rec["api_beat_age_s"] == 400.0


def test_the_weekly_summary_does_not_carry_command_lines():
    rec = {"ts": "2026-11-02T10:00:00Z", "machine": {"cpu": 99.0, "ram_free_mb": 900},
           "eim": {"cpu": 1.0}, "roles": {}, "others": [{"name": "python.exe", "cpu": 90.0}],
           "foreign": [{"cmd": "python secreto.py", "cwd": "C:\\privado", "name": "python.exe"}]}
    text = json.dumps(usage_summary.day_summary([rec], "2026-11-02"), ensure_ascii=False)
    assert "secreto" not in text and "privado" not in text
