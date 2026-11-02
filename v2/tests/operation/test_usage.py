"""Registro de consumo (T127): quién es quién sin línea de órdenes, CPU por diferencia de
contadores, archivo diario con retención y resumen cruzado con la captura HFT."""

import json
import os
import socket
import sys
import time
from types import SimpleNamespace

import pytest

from eim.operation import report, usage, usage_summary
from eim.operation.usage_win import FILETIME_UNIX_S, Proc
from eim.operation.watchdog import instance_lock

MB = 1 << 20
T0 = 1_793_600_000.0                      # 2026-11-02 06:13:20 UTC


def ft(unix_s: float) -> int:
    return int((unix_s + FILETIME_UNIX_S) * 1e7)


def proc(pid, ppid, name, born=T0 - 3600, cpu=0, ram=50 * MB, commit=200 * MB, prio=6):
    return Proc(pid, ppid, name, 0, prio, ft(born), cpu, ram, commit)


def launcher(pid, ppid, born):
    return proc(pid, ppid, "python.exe", born, ram=MB // 3, commit=MB * 7 // 10)


def tree() -> dict[int, Proc]:
    ps = [
        launcher(10, 1, T0 - 100), proc(11, 10, "python.exe", T0 - 99),     # vigilante HFT
        launcher(12, 11, T0 - 98), proc(13, 12, "python.exe", T0 - 97, prio=10),  # captura
        proc(14, 10, "conhost.exe", T0 - 100, commit=MB),
        launcher(21, 2, T0 - 90), proc(20, 21, "python.exe", T0 - 89),        # API (puerto)
        proc(30, 3, "cmd.exe", T0 - 80), proc(31, 30, "node.exe", T0 - 79),  # npm run dev
        proc(32, 31, "cmd.exe", T0 - 78), proc(33, 32, "node.exe", T0 - 77),  # vite (5173)
        proc(34, 33, "esbuild.exe", T0 - 76),
        proc(40, 4, "python.exe", T0 - 70),                                   # ajeno
        proc(42, 4, "cmd.exe", T0 - 70), proc(41, 42, "node.exe", T0 - 69),   # ajeno
        proc(50, 13, "python.exe", T0 - 500),      # PID 13 reutilizado: no es su hijo
        proc(60, 5, "ollama.exe", T0 - 60), proc(61, 60, "ollama_llama_server.exe", T0 - 59),
    ]
    return {p.pid: p for p in ps}


def test_attribute_without_command_lines():
    roles = usage.attribute(tree(), {13: "hft_collector"}, {8000: 20, 5173: 33, 9999: 40})
    assert {p: roles.get(p) for p in (13, 12, 11, 10, 14)} == {
        13: "hft_collector", 12: "hft_collector",          # el servicio y su lanzador
        11: "hft_watchdog", 10: "hft_watchdog", 14: "hft_watchdog"}  # el vigilante y lo suyo
    assert roles[20] == roles[21] == "api"
    assert {roles[p] for p in (30, 31, 32, 33, 34)} == {"web"}
    assert roles[60] == roles[61] == "ollama"
    assert not {40, 41, 42, 50} & set(roles)               # ajenos y PID reutilizado


def test_spool_roles_need_a_file_written_after_birth(tmp_path):
    procs = {7: proc(7, 1, "python.exe", born=T0), 8: proc(8, 1, "python.exe", born=T0),
             9: proc(9, 1, "node.exe", born=T0 - 9000)}
    for name, mtime in (("api.20261102.7.jsonl", T0 + 60), ("collector.20261031.8.jsonl", T0 - 9e4),
                        ("web.20261102.9.jsonl", T0), ("basura.jsonl", T0), ("x.y.z.jsonl", T0)):
        (tmp_path / name).write_text("{}\n")
        os.utime(tmp_path / name, (mtime, mtime))
    assert usage.spool_roles(tmp_path, procs) == {7: "api"}   # 8: PID reutilizado; 9: no es Python
    assert usage.spool_roles(tmp_path / "no_existe", procs) == {}


def test_record_cpu_is_share_of_the_whole_machine():
    a = proc(13, 12, "python.exe", cpu=10 * 10**7, prio=10)
    b = proc(70, 1, "chrome.exe", cpu=4 * 10**7, ram=900 * MB)
    c = proc(71, 1, "chrome.exe", born=T0 - 10, cpu=3 * 10**7)          # nació entre muestras
    d = proc(72, 1, "Memory Compression", cpu=0, ram=1200 * MB)
    idle = proc(0, 0, "System Idle Process", cpu=99 * 10**9)
    procs = {p.pid: p for p in (a, b, c, d, idle)}
    prev = {(13, a.created): 10 * 10**7 - 30 * 10**7, (70, b.created): 4 * 10**7}
    rec = usage.record(T0, 30.0, procs, prev, T0 - 30, {13: "hft_collector"}, 41.234,
                       {"ram_free_mb": 6000}, {"queue": 0}, ncpu=4, top=1)
    g = rec["roles"]["hft_collector"]
    assert g["cpu"] == 25.0 and g["prio"] == 10 and g["pids"] == [13]   # un núcleo de cuatro
    assert rec["eim"] == {"n": 1, "cpu": 25.0, "ram_mb": 50.0}
    assert [o["name"] for o in rec["others"]] == ["chrome.exe", "Memory Compression"]
    assert rec["others"][0] == {"name": "chrome.exe", "n": 2, "cpu": 2.5, "ram_mb": 950.0,
                                "commit_mb": 400.0, "prio": 6}
    assert rec["machine"] == {"cpu": 41.23, "ram_free_mb": 6000} and rec["hft"] == {"queue": 0}
    assert rec["ts"] == time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(T0))


def fake_backend(steps):
    it = iter(steps)
    state = {}

    def snapshot():
        state["cur"] = next(it)
        return state["cur"][0]

    return SimpleNamespace(snapshot=snapshot, system_times=lambda: state["cur"][1],
                           memory=lambda: {"ram_free_mb": 5000}, listeners=lambda ports: {})


def test_sampler_writes_one_line_per_sample_and_prunes(tmp_path):
    p1, p2 = proc(13, 1, "python.exe", cpu=0), proc(13, 1, "python.exe", cpu=6 * 10**7)
    s = usage.Sampler(tmp_path, backend=fake_backend([({13: p1}, (0, 0)),
                                                      ({13: p2}, (3 * 10**8, 12 * 10**8))]),
                      ncpu=4)
    assert s.sample(T0 - 30) is None                       # la primera solo es referencia
    rec = s.sample(T0)
    assert rec["machine"]["cpu"] == 25.0 and rec["others"][0]["cpu"] == 5.0
    path = usage.append(tmp_path, rec)
    usage.append(tmp_path, rec)
    assert path.name == rec["ts"][:10] + ".jsonl"
    assert len(usage_summary.load_day(tmp_path, rec["ts"][:10])) == 2
    d = usage.usage_dir(tmp_path)
    old, closed = d / "2026-09-01.jsonl.gz", d / "2026-10-31.jsonl"
    old.write_text("x")
    closed.write_text(json.dumps(rec) + "\n" + "{a medio escribir")
    (d / "notas.txt").write_text("x")
    assert usage.prune(tmp_path, 30, T0) == 1 and not old.exists() and path.exists()
    assert not closed.exists() and (d / "2026-10-31.jsonl.gz").exists()   # día cerrado: comprimido
    assert usage_summary.load_day(tmp_path, "2026-10-31") == [rec]
    assert usage.prune(tmp_path, 30, T0) == 0 and (d / "notas.txt").exists()


def rec_at(hh: str, mm: int, cpu: float, ram_free: int = 6000) -> dict:
    return {"ts": f"2026-11-02T{hh}:{mm // 2:02d}:{mm % 2 * 30:02d}Z",
            "machine": {"cpu": cpu, "ram_free_mb": ram_free}, "eim": {"cpu": 5.0},
            "roles": {"hft_collector": {"cpu": 1.0}, "collector": {"cpu": 4.0}},
            "others": [{"name": "pytest", "cpu": cpu - 5}]}


def test_day_summary_crosses_saturation_with_lost_hft_hours():
    recs = ([rec_at("13", i, 95.0) for i in range(120)]
            + [rec_at("14", i, 20.0) for i in range(120)]
            + [rec_at("15", i, 30.0) for i in range(10)]
            + [rec_at("16", i, 10.0, ram_free=700 if i == 5 else 6000) for i in range(120)])
    hft = {"13": False, "14": False, "15": False, "16": True}
    d = usage_summary.day_summary(recs, "2026-11-02", hft)
    assert d["saturated_hours"] == ["13", "16"]            # CPU en la 13; RAM en la 16
    assert d["hft"] == {"hours": 4, "incomplete": ["13", "14", "15"],
                        "incomplete_saturated": ["13"], "incomplete_unlogged": ["15"]}
    assert d["cpu"]["max"] == 95.0 and d["peak"]["top"] == "pytest"
    assert d["ram_free_min_mb"] == 700 and d["roles_cpu_mean"] == {"collector": 4.0,
                                                                   "hft_collector": 1.0}
    md = "\n".join(report._usage_lines([d]))
    assert "Horas saturadas: 13, 16" in md
    assert "3 de 4 horas incompletas (13, 14, 15), 1 con el equipo saturado (13)" in md
    assert "1 sin registro (15)" in md


def test_summaries_read_the_qc_files_and_never_break_the_report(tmp_path, monkeypatch):
    qc = tmp_path / "micro_hft" / "qc" / "symbol=BTCUSDT" / "date=2026-11-02"
    qc.mkdir(parents=True)
    (qc / "hour=02.json").write_text(json.dumps({"complete": False}))
    (qc / "hour=03.json").write_text(json.dumps({"complete": True}))
    (qc / "hour=04.json").write_text("{roto")
    assert usage_summary.hft_hours(tmp_path, "BTCUSDT", "2026-11-02") == {"02": False, "03": True}
    t0 = int(T0 * 1000) - 86_400_000
    days = usage_summary.for_report(tmp_path, t0, int(T0 * 1000), ("BTCUSDT",))
    assert [d["day"] for d in days] == ["2026-11-02"] and days[0]["samples"] == 0
    assert "sin registro de consumo; captura HFT: 1 de 2 horas" in "\n".join(
        report._usage_lines(days))
    assert report._usage_lines([])[-1].startswith("Sin registro de consumo")
    monkeypatch.setattr(usage_summary, "week_summary", lambda *a: 1 / 0)
    assert "ZeroDivisionError" in usage_summary.for_report(tmp_path, t0, t0, ())[0]["error"]


def test_a_second_sampler_does_not_start(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(usage.usage_win, "supported", lambda: True)
    lock = instance_lock(usage.usage_dir(tmp_path) / "usage.lock")
    try:
        assert usage.run(tmp_path) == 4
    finally:
        lock.close()
    assert "Ya hay un registro de consumo" in capsys.readouterr().err


win_only = pytest.mark.skipif(sys.platform != "win32", reason="lectura de procesos de Windows")


@win_only
def test_windows_backend_sees_this_process_and_its_port():
    from eim.operation import usage_win

    me = usage_win.snapshot()[os.getpid()]
    assert me.name.lower().startswith("python") and me.ppid == os.getppid()
    assert me.cpu > 0 and me.commit > me.ram > 0 and abs(me.created_s - time.time()) < 86400
    busy, total = usage_win.system_times()
    assert 0 <= busy <= total
    assert usage_win.memory()["ram_total_mb"] > usage_win.memory()["ram_free_mb"] > 0
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen()
        port = srv.getsockname()[1]
        assert usage_win.listeners(frozenset({port})) == {port: os.getpid()}


@win_only
def test_run_once_prints_a_sample_and_writes_nothing(tmp_path, capsys):
    assert usage.main(["run", "--once", "--every", "0.3", "--data-dir", str(tmp_path)]) == 0
    rec = json.loads(capsys.readouterr().out)
    assert rec["machine"]["ram_total_mb"] > 0 and set(rec) >= {"roles", "others", "hft"}
    assert not (tmp_path / "operation").exists() and not (tmp_path / "obs").exists()
