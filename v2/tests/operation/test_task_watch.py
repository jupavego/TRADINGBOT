"""Si la tarea del bucle de operación muere dentro de la API, deja rastro (registro, alerta,
estado `caido`); si la cancela el apagado normal, no avisa de nada. Sin red."""

import asyncio
import json
import time

import pytest

from eim.api.config import Settings
from eim.operation import alerts as A
from eim.operation.supervisor import Supervisor
from eim.operation.task_watch import STOPPED, watch_supervisor
from tests.local_client import LocalClient
from tests.operation.helpers import Market, Rig


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path, Market())
    r.build()
    yield r
    r.close()


def events(root) -> list[dict]:
    logs = sorted((root / "operation" / "logs").glob("op-*.jsonl"))
    return [json.loads(x) for f in logs for x in f.read_text(encoding="utf-8").splitlines()]


def run_watched(op, coro) -> asyncio.Task:
    async def main():
        task = watch_supervisor(asyncio.create_task(coro), op)
        await asyncio.wait([task])
        await asyncio.sleep(0)                      # el aviso corre como callback del bucle
        return task

    return asyncio.run(main())


def test_dead_supervisor_leaves_log_alert_and_state(rig, capsys):
    async def broken_sleep(s):
        raise RuntimeError("bucle roto")            # fuera del try del ciclo: mata la tarea

    run_watched(rig.op, Supervisor(rig.op, sleep=broken_sleep).run())
    st = rig.op.status
    assert st["state"] == "caido" and st["last_error"] == "RuntimeError: bucle roto"
    assert st["cycles"] == 1
    dead = [e for e in events(rig.root) if e["event"] == STOPPED]
    assert len(dead) == 1 and dead[0]["level"] == "error" and dead[0]["cycles"] == 1
    alerts = [a for a in rig.sent if a.kind == A.SERVICE]
    assert [(a.level, a.title) for a in alerts] == [(A.CRITICAL, "El bucle de operación se detuvo")]
    assert "RuntimeError: bucle roto" in alerts[0].detail
    assert "RuntimeError: bucle roto" in capsys.readouterr().err  # traza para el vigilante


def test_cancelled_supervisor_is_silent(rig):
    async def main():
        task = watch_supervisor(asyncio.create_task(asyncio.Event().wait()), rig.op)
        await asyncio.sleep(0)
        task.cancel()                               # lo que hace el apagado de la API
        await asyncio.wait([task])
        await asyncio.sleep(0)

    asyncio.run(main())
    assert rig.op.status["state"] == "iniciando" and rig.sent == []
    assert STOPPED not in [e["event"] for e in events(rig.root)]


class Quiet:
    name = "quiet"

    async def stream(self, symbol, timeframe):
        await asyncio.sleep(3600)
        yield


def test_api_lifespan_watches_the_supervisor_task(tmp_path, monkeypatch):
    """`create_app` engancha el aviso a la tarea que arranca con la API."""
    import eim.api.main as main

    class DiesAtStart:
        def __init__(self, op):
            self.op = op

        async def run(self):
            raise RuntimeError("muere al arrancar")

    monkeypatch.setenv("EIM_NOTIFY", "0")           # sin globos de Windows en la prueba
    monkeypatch.setattr(main, "Supervisor", DiesAtStart)
    cfg = Settings(data_dir=tmp_path, operate=True, execution="paper", calendar=False,
                   arbitrage=False, paper=False, auto_history=False)
    app = main.create_app(cfg, source=Quiet(), operation_provider=Market())
    with LocalClient(app) as c:
        deadline = time.time() + 5
        while app.state.operation.status["state"] != "caido" and time.time() < deadline:
            time.sleep(0.05)
        body = c.get("/v2/operation").json()
    assert body["service"]["state"] == "caido"
    assert body["service"]["last_error"] == "RuntimeError: muere al arrancar"
    assert STOPPED in [e["event"] for e in events(tmp_path)]
