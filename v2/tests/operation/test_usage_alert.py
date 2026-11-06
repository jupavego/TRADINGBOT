"""T141: el aviso temprano. Lo que viaja en las copias solo lleva las causas, no las órdenes."""

import pytest

from eim.operation import usage_alert
from eim.operation.alerts import WARN

T0 = 1_793_600_000.0                      # 2026-11-02 06:13:20 UTC


def sample(t_s=0, cpu=40.0, commit=20_000, api_ram=1200.0, api_cpu=2.0, api=True, beat=None,
           foreign=None):
    roles = {"api": {"n": 2, "cpu": api_cpu, "ram_mb": api_ram, "commit_mb": 2400.0, "prio": 6}}
    rec = {"t": int(T0 * 1000) + t_s * 30_000, "machine": {"cpu": cpu, "commit_mb": commit},
           "roles": roles if api else {},
           "others": [{"name": "chrome.exe", "n": 9, "cpu": 8.0, "commit_mb": 3000.0}]}
    return {**rec, **({"api_beat_age_s": beat} if beat is not None else {}),
            **({"foreign": foreign} if foreign else {})}


@pytest.mark.parametrize("kw, word", [
    ({"commit": 36_000}, "memoria comprometida 35 GB"),
    ({"api_ram": 200.0}, "solo conserva 200 MB"),
    ({"cpu": 95.0, "api_cpu": 0.3}, "CPU del equipo al 95 %"),
    ({"beat": 300.0}, "latido de la API parado 300 s"),
])
def test_each_measured_limit_is_a_cause(kw, word):
    assert any(word in c for c in usage_alert.causes(sample(**kw)))


@pytest.mark.parametrize("kw", [
    {}, {"commit": 35_999}, {"api_ram": 201.0}, {"cpu": 94.9, "api_cpu": 0.1},
    {"cpu": 100.0, "api_cpu": 0.31}, {"beat": 299.0}, {"beat": 3601.0},
])
def test_just_inside_the_limits_there_is_no_cause(kw):
    assert usage_alert.causes(sample(**kw)) == []


def test_without_api_only_the_memory_counts():
    assert usage_alert.causes(sample(api=False, api_ram=1.0, cpu=100.0, beat=500.0)) == []
    assert len(usage_alert.causes(sample(api=False, commit=40_000))) == 1


def test_warns_after_three_samples_once_and_resolves_after_ten_clean():
    got = []
    w = usage_alert.EarlyWarning([got.append])
    seq = [sample(i, commit=40_000) for i in range(6)]
    out = [w.update(r) for r in seq]
    assert out[:2] == [None, None] and out[2].level == WARN and out[2:] == [out[2], *[None] * 3]
    assert out[2].key == usage_alert.KEY and "memoria comprometida" in out[2].detail
    assert len(got) == 1 and w.active
    clean = [w.update(sample(6 + i)) for i in range(10)]
    assert clean[:9] == [None] * 9 and clean[9].resolved and not w.active and len(got) == 2


def test_a_single_clean_sample_does_not_close_the_episode_nor_two_bad_ones_open_it():
    got = []
    w = usage_alert.EarlyWarning([got.append])
    for i, c in enumerate([40_000, 40_000, 20_000, 40_000, 40_000, 20_000]):
        w.update(sample(i, commit=c))
    assert got == [] and not w.active
    for i in range(6, 9):
        w.update(sample(i, commit=40_000))
    w.update(sample(9))
    w.update(sample(10, commit=40_000))
    assert len(got) == 1 and w.active


def test_every_episode_warns_even_soon_after_a_resolved_one():
    got = []
    w = usage_alert.EarlyWarning([got.append])
    t = 0

    def episode(gap):
        nonlocal t
        t += gap
        for _ in range(3):
            w.update(sample(t, commit=40_000))
            t += 1
        for _ in range(10):
            w.update(sample(t))
            t += 1

    episode(0)                                              # aviso y resuelta
    assert len(got) == 2
    episode(0)                                              # a los pocos minutos: 5-nov 04:03
    assert len(got) == 4 and not got[2].resolved and got[3].resolved and not w.active


def test_the_culprit_goes_to_the_toast_but_not_to_what_travels():
    logged, shown = [], []
    w = usage_alert.EarlyWarning([logged.append], shown.append)
    tree = {"pid": 7, "name": "python.exe", "n": 8, "cpu": 62.0, "ram_mb": 2300.0,
            "commit_mb": 4500.0, "prio": 8, "cmd": "python -I 23_modelo.py --procesos 7",
            "cwd": "C:\\OPERACION\\PROTOTIPO"}
    for i in range(3):
        a = w.update(sample(i, cpu=100.0, api_cpu=0.1, foreign=[tree]))
    assert "23_modelo" in shown[0].detail and "PROTOTIPO" in shown[0].detail
    assert "23_modelo" not in logged[0].detail and "PROTOTIPO" not in logged[0].detail
    assert "23_modelo" not in a.detail


def test_culprit_follows_the_kind_of_pressure():
    small = {"pid": 7, "name": "node.exe", "n": 1, "cpu": 6.0, "ram_mb": 300.0,
             "commit_mb": 400.0, "cmd": "node vite.js", "cwd": None}
    assert usage_alert.culprit(sample(commit=40_000, foreign=[small])).startswith("chrome.exe")
    assert usage_alert.culprit(sample(foreign=[{**small, "cpu": 60.0}])).startswith("node vite.js")
    big = {**small, "name": "chrome.exe", "commit_mb": 100.0, "cmd": "chrome.exe --x"}
    assert usage_alert.culprit(sample(commit=40_000, foreign=[big])).startswith("chrome.exe --x")


def test_culprit_falls_back_to_the_name_when_there_is_no_order():
    assert usage_alert.culprit(sample()).startswith("chrome.exe (9 procesos")
    bare = {"pid": 7, "name": "python.exe", "n": 1, "cpu": 9.0, "ram_mb": 300.0, "cmd": None,
            "cwd": None}
    assert usage_alert.culprit(sample(foreign=[bare])).startswith("python.exe (1 procesos")
    assert usage_alert.culprit({"machine": {}}) == "sin identificar"


def test_a_broken_channel_does_not_stop_the_warning():
    def broken(a):
        raise RuntimeError("sin bandeja")

    got = []
    w = usage_alert.EarlyWarning([broken, got.append], broken)
    for i in range(3):
        w.update(sample(i, commit=40_000))
    assert len(got) == 1 and len(w.errors) == 2 and "sin bandeja" in w.errors[0]


def test_the_service_warning_writes_causes_to_the_operation_log(tmp_path, monkeypatch):
    monkeypatch.setenv("EIM_NOTIFY", "0")
    w = usage_alert.for_service(tmp_path)
    tree = {"pid": 7, "name": "python.exe", "n": 8, "cpu": 62.0, "ram_mb": 2300.0,
            "cmd": "python -I secreto.py", "cwd": "C:\\privado"}
    for i in range(3):
        w.update(sample(i, commit=40_000, foreign=[tree]))
    logs = list((tmp_path / "operation" / "logs").glob("op-*.jsonl"))
    text = logs[0].read_text("utf-8")
    assert '"event": "alerta"' in text and "memoria comprometida" in text
    assert "secreto" not in text and "privado" not in text
