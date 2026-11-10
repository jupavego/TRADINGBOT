"""T141: cada ciclo lento, reinicio y arranque lento, cruzados con el consumo del equipo."""

import json
from datetime import UTC, datetime

from eim.operation import usage, usage_incidents

T0 = 1_793_600_000.0                      # 2026-11-02 06:13:20 UTC


def write_ops(tmp_path, rows):
    d = tmp_path / "operation" / "logs"
    d.mkdir(parents=True)
    with (d / "op-2026-11-02.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
        f.write("{a medio escribir\n")


BASE = int(T0 * 1000)
OPS = [
    {"t": BASE + 1_000, "event": "ciclo", "cycle_t": BASE},                      # normal
    {"t": BASE + 500_000, "event": "ciclo", "cycle_t": BASE + 100_000},          # 400 s
    {"t": BASE + 2_000_000, "event": "proceso_reiniciado",
     "reason": "latido detenido 932 s"},
    {"t": BASE + 2_010_000, "event": "proceso_lanzado"},
    {"t": BASE + 2_440_000, "event": "servicio_iniciado"},                       # 430 s
    {"t": BASE + 3_000_000, "event": "proceso_reiniciado",
     "reason": "el proceso terminó (código 1)"},
    {"t": BASE + 3_010_000, "event": "proceso_lanzado"},
    {"t": BASE + 3_030_000, "event": "servicio_iniciado"},                       # 20 s: normal
    {"t": BASE + 3_100_000, "event": "decision"},
]


def test_find_lists_slow_cycles_restarts_and_slow_boots():
    got = usage_incidents.find(OPS)
    assert [(x["kind"], x["t1"] - x["t0"]) for x in got] == [
        ("ciclo_lento", 400_000), ("reinicio_latido", 932_000), ("arranque_lento", 430_000),
        ("reinicio_salida", 120_000)]
    assert [x["kind"] for x in usage_incidents.find(OPS, slow_s=500)] == [
        "reinicio_latido", "reinicio_salida"]


def usage_sample(t_ms, cpu, api_ram, api_cpu=0.1, foreign=None, faults=100, hft=None):
    rec = {"t": t_ms, "ts": datetime.fromtimestamp(t_ms / 1000, UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), "dt_s": 30.0,
        "machine": {"cpu": cpu, "commit_mb": 30_000, "commit_limit_mb": 35_000, "ram_free_mb": 900},
        "eim": {"cpu": 1.0}, "hft": hft or {"queue": 2},
        "roles": {"api": {"n": 2, "cpu": api_cpu, "ram_mb": api_ram, "commit_mb": 2400.0,
                          "prio": 6, "faults": faults},
                  "hft_collector": {"n": 2, "cpu": 4.0, "ram_mb": 150.0, "commit_mb": 300.0,
                                    "prio": 10}},
        "others": [{"name": "python.exe", "n": 12, "cpu": 70.0, "ram_mb": 2300.0,
                    "commit_mb": 4500.0, "prio": 8},
                   {"name": "chrome.exe", "n": 9, "cpu": 5.0, "ram_mb": 900.0,
                    "commit_mb": 3000.0, "prio": 8}]}
    return {**rec, **({"foreign": foreign} if foreign else {})}


def test_cross_says_who_was_spending_and_what_happened_to_the_api():
    tree = {"pid": 7, "name": "python.exe", "n": 8, "cpu": 60.0, "ram_mb": 2000.0,
            "commit_mb": 4000.0, "prio": 8, "cmd": "python -I modelo.py --procesos 7",
            "cwd": "C:\\PROTOTIPO"}
    bigger = {**tree, "n": 9, "cpu": 75.0, "ram_mb": 2300.0}
    samples = [usage_sample(BASE, 100.0, 1400.0, foreign=[tree], faults=100),
               usage_sample(BASE + 30_000, 100.0, 500.0, foreign=[bigger], faults=900,
                            hft={"queue": 3000})]
    c = usage_incidents.cross(samples, BASE - 1, BASE + 40_000)
    assert c["samples"] == 2 and c["machine"]["cpu_mean"] == 100.0
    assert c["machine"]["commit_max_mb"] == 30_000 and c["machine"]["ram_free_min_mb"] == 900
    assert c["api"]["ram_first_mb"] == 1400.0 and c["api"]["ram_min_mb"] == 500.0
    assert c["api"]["hard_faults"] == 800 and c["api"]["prio"] == 6
    assert c["capture"] == {"ram_min_mb": 150.0, "queue_max": 3000}
    assert c["top_cpu"][0] == {"name": "python.exe", "cpu_mean": 70.0}
    assert c["top_commit"][0] == {"name": "python.exe", "commit_max_mb": 4500.0}
    f = c["foreign"][0]
    assert f["cmd"].endswith("--procesos 7") and f["n"] == 9 and f["cpu_max"] == 75.0
    assert f["ram_max_mb"] == 2300.0 and f["cwd"] == "C:\\PROTOTIPO"


def test_hard_faults_survive_an_api_restart_inside_the_window():
    samples = [usage_sample(BASE + i * 30_000, 90.0, 500.0, faults=f)
               for i, f in enumerate((1000, 1500, 20, 120))]
    assert usage_incidents.cross(samples, BASE - 1, BASE + 100_000)["api"]["hard_faults"] == 600


def test_cross_without_samples_says_so_and_a_short_stretch_looks_around():
    assert usage_incidents.cross([], BASE, BASE + 1) == {"samples": 0}
    near = [usage_sample(BASE + 30_000, 90.0, 800.0)]
    assert usage_incidents.cross(near, BASE, BASE + 1)["samples"] == 1


def test_samples_from_before_t141_still_cross_but_without_names():
    old = usage_sample(BASE, 100.0, 500.0)
    del old["roles"]["api"]["faults"]
    c = usage_incidents.cross([old], BASE - 1, BASE + 1)
    assert c["foreign"] == [] and c["api"]["hard_faults"] is None
    assert c["top_cpu"][0]["name"] == "python.exe"


def test_the_command_crosses_the_real_files_and_prints_json(tmp_path, capsys, monkeypatch):
    write_ops(tmp_path, OPS)
    usage.append(tmp_path, usage_sample(BASE + 200_000, 100.0, 500.0))
    usage.append(tmp_path, usage_sample(BASE + 1_500_000, 100.0, 40.0))
    monkeypatch.setattr(usage.time, "time", lambda: T0 + 4000)
    assert usage.main(["incidents", "--days", "2", "--data-dir", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    # Dos muestras a 1300 s una de otra, y la última 2500 s antes de «ahora»: son dos silencios del
    # propio registro (T148 E2), el segundo todavía abierto. Se comprueban y se apartan.
    gaps = [x for x in out if x["kind"] == "apagon_registro"]
    assert [g["dur_s"] for g in gaps] == [1300, 2500] and gaps[1]["edges"]["first_after"] is None
    out = [x for x in out if x["kind"] != "apagon_registro"]
    assert [x["kind"] for x in out] == ["ciclo_lento", "reinicio_latido", "arranque_lento",
                                        "reinicio_salida"]
    assert out[0]["dur_s"] == 400 and out[0]["api"]["ram_min_mb"] == 500.0
    assert out[1]["detail"] == "latido detenido 932 s" and out[1]["api"]["ram_min_mb"] == 40.0
    assert out[2]["samples"] == 0
