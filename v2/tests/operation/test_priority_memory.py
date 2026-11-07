"""Memoria y E/S de los recolectores (T141, ◆B). `apply` nunca toca los servicios de verdad aquí:
las pruebas sustituyen la lista de servicios o actúan sobre un proceso hijo propio."""

import json
import subprocess
import sys
import time

import pytest

from eim.operation import priority_memory as pm

win = pytest.mark.skipif(sys.platform != "win32", reason="prioridades de Windows")
DEAD_PID = 0xFFFFFF0


def row(role, pid=1, cpu_prio=10):
    return {"role": role, "pid": pid, "cpu_prio": cpu_prio, "session": 1}


def test_only_the_live_collectors_are_targets():
    rows = [row("hft_collector", 1), row("liq_collector", 2), row("collector", 3),
            row("liq_collector", 4, cpu_prio=6),         # su lanzador, que solo espera
            row("api", 5), row("leaders", 6), row("hft_watchdog", 7), row("web", 8),
            row("desconocido", 9)]
    assert [r["pid"] for r in pm.targets(rows)] == [1, 2, 3]


def fake_process(monkeypatch, *, raises=True, after="5/2"):
    state = {"calls": []}

    def read(pid):
        raised = pid in state["calls"]
        return {"memory": 5 if raised else 2, "io": 2 if raised else 1,
                "threads": {after: 3} if raised else {"2/1": 3}}

    def raise_normal(pid=None):
        state["calls"].append(pid)
        return raises

    monkeypatch.setattr(pm, "read", read)
    monkeypatch.setattr(pm, "raise_normal", raise_normal)
    return state


def test_apply_raises_only_the_collectors_and_checks_every_thread(monkeypatch):
    state = fake_process(monkeypatch)
    out = pm.apply([row("hft_collector", 1), row("api", 5)])
    assert state["calls"] == [1] and len(out) == 1 and out[0]["ok"]
    assert out[0]["before"]["threads"] == {"2/1": 3} and out[0]["after"]["threads"] == {"5/2": 3}


@pytest.mark.parametrize("kw", [{"raises": False}, {"after": "2/1"}])
def test_apply_is_not_ok_unless_windows_did_it_on_every_thread(monkeypatch, kw):
    fake_process(monkeypatch, **kw)
    assert not pm.apply([row("hft_collector", 1)])[0]["ok"]


def test_the_command_reports_and_its_exit_code_says_if_it_worked(monkeypatch, capsys):
    fake_process(monkeypatch)
    monkeypatch.setattr(pm, "services", lambda d: [row("hft_collector", 1), row("api", 5)])
    assert pm.main(["apply"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["role"] == "hft_collector"
    assert pm.main(["show"]) == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 2    # enseña todos, cambia uno
    monkeypatch.setattr(pm, "services", lambda d: [row("api", 5)])
    assert pm.main(["apply"]) == 1
    assert "No hay recolectores" in capsys.readouterr().err


@win
def test_a_change_from_outside_reaches_a_running_process_and_its_threads():
    code = ("import threading, time\nfor _ in range(2):\n"
            "    threading.Thread(target=time.sleep, args=(60,), daemon=True).start()\n"
            "print('listo', flush=True)\ntime.sleep(60)\n")
    child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)  # noqa: S603
    try:
        child.stdout.readline()
        assert pm.set_levels(child.pid, 2, 1)
        low = pm.read(child.pid)
        assert (low["memory"], low["io"]) == (2, 1) and set(low["threads"]) == {"2/1"}
        assert sum(low["threads"].values()) >= 3            # el principal y los dos lanzados
        assert pm.raise_normal(child.pid)
        high = pm.read(child.pid)
        assert (high["memory"], high["io"]) == (5, 2) and set(high["threads"]) == {"5/2"}
    finally:
        child.kill()
        child.wait()
    time.sleep(0.05)
    assert pm.read(child.pid) is None or child.poll() is not None


@win
def test_a_missing_process_does_not_raise():
    assert pm.read(DEAD_PID) is None
    assert pm.set_levels(DEAD_PID, 5, 2) is False
    assert pm.raise_normal(DEAD_PID) is False


def test_outside_windows_it_does_nothing(monkeypatch):
    monkeypatch.setattr(pm.sys, "platform", "linux")
    assert pm.set_levels(None, 5, 2) is False and pm.read(1) is None
