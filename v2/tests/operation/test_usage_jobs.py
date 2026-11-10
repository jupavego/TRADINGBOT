"""T149: `usage incidents` nombra el trabajo de la cola, no el `submit` que hace de ejecutor."""

import json
from datetime import UTC, datetime

from eim.operation import usage, usage_alert, usage_incidents, usage_jobs

DAY = "2026-11-09"
T = 1_794_220_694_641                     # 2026-11-09 10:38:14 UTC: arranca t143-maker
SUBMIT = ("python.exe -X utf8 -m eim.operation.jobs --data-dir C:/x/data submit "
          "--name gate-t143-final --cwd C:/x")


def write_jobs(tmp_path, rows, day=DAY):
    d = tmp_path / "jobs" / "log"
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{day}.jsonl").open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
        f.write("{roto\n")


LOG = [
    {"t": T - 3_000_000, "job": "gate-1", "name": "gate-t143-final", "event": "encolado",
     "cmd": "python -m pytest -q"},
    {"t": T - 2_000_000, "job": "gate-1", "name": "gate-t143-final", "event": "arranca"},
    {"t": T, "job": "gate-1", "name": "gate-t143-final", "event": "termina"},
    {"t": T - 1_000_000, "job": "maker-1", "name": "t143-maker", "event": "encolado",
     "cmd": "C:/v/python.exe -I scripts/t143_maker.py --out reports/t143_maker"},
    {"t": T, "job": "maker-1", "name": "t143-maker", "event": "arranca"},
    {"t": T + 20_000_000, "job": "maker-1", "name": "t143-maker", "event": "termina"},
]


def tree(n=4, cmd=SUBMIT, ram=6849.1, pid=35188):
    return {"pid": pid, "name": "python.exe", "n": n, "cpu": 0.0, "ram_mb": ram,
            "commit_mb": 18439.6, "prio": 8, "cmd": cmd, "cwd": "C:\\x"}


def test_runs_come_from_the_job_log_and_cross_midnight(tmp_path):
    write_jobs(tmp_path, LOG)
    write_jobs(tmp_path, [{"t": T - 50_000_000, "job": "noche", "name": "noche",
                           "event": "arranca"}], day="2026-11-08")   # la víspera, sin cerrar
    runs = usage_jobs.load_runs(tmp_path, [DAY])
    assert [(r["id"], r["t1"] is None) for r in runs] == [("noche", True), ("gate-1", False),
                                                          ("maker-1", False)]
    assert runs[2]["cmd"] == "python.exe -I scripts/t143_maker.py --out reports/t143_maker"
    closed = runs[1:]
    assert usage_jobs.running_at(closed, T)["id"] == "maker-1"       # el gate ya terminó
    assert usage_jobs.running_at(closed, T - 1)["id"] == "gate-1"
    assert usage_jobs.running_at(closed, T + 30_000_000) is None
    assert usage_jobs.running_at(runs, T + 30_000_000)["id"] == "noche"


def test_only_an_executor_tree_is_relabelled(tmp_path):
    write_jobs(tmp_path, LOG)
    runs = usage_jobs.load_runs(tmp_path, [DAY])
    got = usage_jobs.relabel(tree(), runs, T + 3_600_000)
    assert (got["job"], got["job_id"], got["host_cmd"]) == ("t143-maker", "maker-1", SUBMIT)
    assert got["cmd"].startswith("python.exe -I scripts/t143_maker.py")
    alone = tree(n=1)                                   # un submit que solo espera su turno
    other = tree(cmd="python -I modelo.py --procesos 2")
    assert usage_jobs.relabel(alone, runs, T + 3_600_000) is alone
    assert usage_jobs.relabel(other, runs, T + 3_600_000) is other
    assert usage_jobs.relabel(tree(), runs, T + 30_000_000)["cmd"] == SUBMIT   # nada corría


def test_incidents_name_the_queued_job_not_the_submit(tmp_path, capsys, monkeypatch):
    """El 9-nov a las 12 h: un ciclo lento con 6,8 GB en el árbol del ejecutor."""
    write_jobs(tmp_path, LOG)
    t0 = T + 4_926_000                                   # 12:00:20
    ops = tmp_path / "operation" / "logs"
    ops.mkdir(parents=True)
    (ops / f"op-{DAY}.jsonl").write_text(json.dumps(
        {"t": t0 + 613_000, "event": "ciclo", "cycle_t": t0}) + "\n", encoding="utf-8")
    for i in range(0, 640, 30):
        usage.append(tmp_path, {
            "t": t0 + i * 1000, "ts": datetime.fromtimestamp((t0 + i * 1000) / 1000, UTC)
            .strftime("%Y-%m-%dT%H:%M:%SZ"), "dt_s": 30.0,
            "machine": {"cpu": 50.0, "commit_mb": 30_000, "ram_free_mb": 300},
            "roles": {}, "others": [], "foreign": [tree(ram=6000 + i)]})
    rep = usage_incidents.report(tmp_path, [DAY])
    slow = [x for x in rep if x["kind"] == "ciclo_lento"]
    assert len(slow) == 1 and len(slow[0]["foreign"]) == 1
    f = slow[0]["foreign"][0]
    assert (f["job"], f["job_id"], f["ram_max_mb"]) == ("t143-maker", "maker-1", 6600)
    assert "gate-t143-final" in f["host_cmd"] and "t143_maker.py" in f["cmd"]


def test_the_early_warning_names_the_queued_job_too(tmp_path):
    write_jobs(tmp_path, LOG)
    runs = usage_jobs.load_runs(tmp_path, [DAY])
    rec = {"t": T + 3_600_000, "machine": {"commit_mb": 40_000, "cpu": 50.0},
           "roles": {"api": {"ram_mb": 120.0, "cpu": 0.1}}, "others": [], "foreign": [tree()]}
    said = usage_alert.culprit(rec, runs)
    assert said.startswith("trabajo de la cola «t143-maker» (python.exe -I scripts/t143_maker.py")
    assert "gate-t143-final" not in said
    assert "submit --name gate-t143-final" in usage_alert.culprit(rec)   # sin registro, como antes
