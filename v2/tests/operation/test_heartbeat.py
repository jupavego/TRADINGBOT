"""Latido a prueba de Windows (2026-10-24): un `heartbeat.json` que no se deja reemplazar
(WinError 5: otro proceso lo está leyendo) no mata el bucle de operación, y el vigilante no
confunde una lectura fallida del latido con un latido detenido (T42-12)."""

import asyncio
import json
from pathlib import Path

import pytest

from eim.operation import watchdog
from eim.operation.notify import JsonLog
from eim.operation.supervisor import Supervisor
from eim.operation.watchdog import Watchdog, heartbeat_t, write_heartbeat
from tests.operation.helpers import Market, Rig

REAL_REPLACE = Path.replace


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path, Market())
    r.build()
    yield r
    r.close()


def deny_heartbeat(monkeypatch, times: int | None = None) -> dict:
    """`Path.replace` hacia `heartbeat.json` falla como en Windows (`times` veces; None =
    siempre). El resto de reemplazos (estado del servicio) funciona."""
    calls = {"denied": 0}

    def replace(self, target):
        if Path(target).name == "heartbeat.json" and (times is None or calls["denied"] < times):
            calls["denied"] += 1
            raise PermissionError(13, "Acceso denegado")
        return REAL_REPLACE(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    return calls


def run(rig, cycles: int = 3) -> list[float]:
    waits: list[float] = []

    async def fake_sleep(s):
        waits.append(s)

    asyncio.run(Supervisor(rig.op, max_backoff_s=10, sleep=fake_sleep).run(max_cycles=cycles))
    return waits


def events(rig) -> list[dict]:
    logs = sorted((rig.root / "operation" / "logs").glob("op-*.jsonl"))
    return [json.loads(x) for f in logs for x in f.read_text(encoding="utf-8").splitlines()]


def test_heartbeat_denied_once_is_retried_without_warning(rig, monkeypatch):
    calls = deny_heartbeat(monkeypatch, times=1)
    assert run(rig) == [1.0, 1.0, 1.0]
    st = rig.op.status
    assert st["cycles"] == 3 and st["failures"] == 0 and calls["denied"] == 1
    names = [e["event"] for e in events(rig)]
    assert names.count("ciclo") == 3 and "latido_fallido" not in names
    hb = json.loads((rig.root / "operation" / "heartbeat.json").read_text(encoding="utf-8"))
    assert hb["last_heartbeat"] == rig.now() and hb["cycles"] == 3


def test_heartbeat_always_denied_warns_and_keeps_cycling(rig, monkeypatch):
    calls = deny_heartbeat(monkeypatch)
    assert run(rig) == [1.0, 1.0, 1.0]                      # sin espera creciente
    st = rig.op.status
    assert st["cycles"] == 3 and st["failures"] == 0 and st["state"] == "detenido"
    assert calls["denied"] == 9                             # 3 intentos por ciclo
    ev = events(rig)
    assert [e["event"] for e in ev].count("ciclo") == 3
    warns = [e for e in ev if e["event"] == "latido_fallido"]
    assert len(warns) == 3 and {w["level"] for w in warns} == {"warn"}
    assert warns[0]["error"].startswith("PermissionError")
    assert not (rig.root / "operation" / "heartbeat.json").exists()


def test_errors_outside_the_cycle_do_not_kill_the_loop(rig, monkeypatch):
    """Un fallo inesperado del latido o del aviso de un ciclo fallido tampoco detiene el bucle,
    y la espera creciente no cambia."""
    real_step, real_write = rig.op.step, rig.op.log.write
    n = {"step": 0}

    def step():
        n["step"] += 1
        if n["step"] == 1:
            raise RuntimeError("ciclo roto")
        return real_step()

    def write(event, *a, **kw):
        if event == "ciclo_fallido":
            raise OSError("disco lleno")
        return real_write(event, *a, **kw)

    def heartbeat():
        raise ValueError("latido ilegible")

    monkeypatch.setattr(rig.op, "step", step)
    monkeypatch.setattr(rig.op.log, "write", write)
    monkeypatch.setattr(rig.op, "heartbeat", heartbeat)
    assert run(rig) == [2.0, 1.0, 1.0]
    st = rig.op.status
    assert st["failures"] == 1 and st["cycles"] == 2 and st["consecutive_failures"] == 0
    assert st["next_cycle_at"] is not None


def test_write_heartbeat_retries_then_returns_the_error(tmp_path, monkeypatch):
    hb, naps = tmp_path / "op" / "heartbeat.json", []
    deny_heartbeat(monkeypatch, times=1)
    assert write_heartbeat(hb, {"last_heartbeat": 5}, sleep=naps.append) is None
    assert heartbeat_t(hb) == 5 and naps == [0.05]
    deny_heartbeat(monkeypatch)
    err = write_heartbeat(hb, {"last_heartbeat": 6}, sleep=naps.append)
    assert isinstance(err, PermissionError) and naps == [0.05, 0.05, 0.05]
    assert heartbeat_t(hb) == 5                             # el latido anterior sigue legible


class Proc:
    """Proceso falso vivo hasta la consulta número `polls`."""

    def __init__(self, polls: int) -> None:
        self.left, self.terminated = polls, False

    def poll(self):
        self.left -= 1
        return 0 if self.left <= 0 else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def test_watchdog_keeps_last_good_heartbeat_when_a_read_fails(tmp_path, monkeypatch):
    clock, reads = {"t": 10_000.0}, {"n": 0}

    def read(path):
        reads["n"] += 1          # la 15.ª lectura choca con el reemplazo (150 s tras arrancar)
        return None if reads["n"] == 15 else int(clock["t"] * 1000)

    def sleep(s):
        clock["t"] += s

    monkeypatch.setattr(watchdog, "heartbeat_t", read)
    wd = Watchdog(["x"], {}, tmp_path / "heartbeat.json", JsonLog(tmp_path / "logs"),
                  stale_s=100, check_s=10, clock=lambda: clock["t"], sleep=sleep,
                  notify=lambda a: None)
    proc = Proc(polls=20)
    assert "terminó" in wd._watch(proc) and not proc.terminated     # sin falso «latido detenido»
    assert reads["n"] == 19
