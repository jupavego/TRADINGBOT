"""Recolector de microestructura (T104): cerrojo, reinicio, latido viejo, disco y estado."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from eim.api.micro import build_micro_router
from eim.data.collectors import health, supervise
from eim.data.collectors.binance_ws import Collector
from eim.data.collectors.writer import HourlyWriter
from eim.operation.watchdog import instance_lock

NOW = 1_800_000_000_000


def test_classify_states(tmp_path):
    assert health.classify(None, NOW)[0] == "apagado"
    old = {"last_heartbeat": NOW - 200_000, "last_msg_ms": NOW - 1000}
    assert health.classify(old, NOW)[0] == "apagado"            # latido viejo
    no_msg = {"last_heartbeat": NOW - 1000, "last_msg_ms": None}
    assert health.classify(no_msg, NOW)[0] == "sin_flujo"        # conecta y no entrega
    quiet = {"last_heartbeat": NOW - 1000, "last_msg_ms": NOW - 400_000}
    assert health.classify(quiet, NOW)[0] == "sin_flujo"
    ok = {"last_heartbeat": NOW - 1000, "last_msg_ms": NOW - 2000}
    assert health.classify(ok, NOW) == ("capturando", "ok")
    fresh = {"last_heartbeat": NOW - 1000, "last_msg_ms": None, "started_at": NOW - 5000}
    assert health.problems(str(tmp_path / "otro"), NOW)  # sin latido sí avisa
    health.write_heartbeat(tmp_path, fresh)
    assert not [m for m in health.problems(tmp_path, NOW) if "Microestructura" in m]  # gracia


def test_collector_writes_heartbeat(tmp_path):
    c = Collector(tmp_path, "btcusdt")
    c.heartbeat()
    hb = health.read_heartbeat(tmp_path)
    assert hb["symbol"] == "BTCUSDT" and hb["pid"] == os.getpid() and hb["last_msg_ms"] is None
    c.on_message({"data": {"e": "aggTrade", "a": 1, "T": NOW, "p": "1", "q": "1", "m": False}})
    c.heartbeat()
    hb = health.read_heartbeat(tmp_path)
    assert hb["trades"] == 1 and health.classify(hb, int(time.time() * 1000))[0] == "capturando"


def test_supervisor_lock_and_watchdog(tmp_path):
    got = []

    class Fake:
        def __init__(self, cmd, env, hb, log, **kw):
            got.append((cmd, hb, kw))

        def run(self):
            assert instance_lock(tmp_path / "micro" / "supervisor.lock") is None   # tomado

    assert supervise.supervise(tmp_path, "btcusdt", make_watchdog=Fake) == \
        "vigilante de microestructura detenido"
    ((cmd, hb, kw),) = got
    assert cmd[1:4] == ["-m", "eim.data.collectors.binance_ws", "BTCUSDT"]
    assert hb == tmp_path / "micro" / "heartbeat.json" and kw["stale_s"] == health.STALE_S
    held = instance_lock(tmp_path / "micro" / "supervisor.lock")        # ya hay otro vigilante
    assert "Ya hay un vigilante" in supervise.supervise(tmp_path, "BTCUSDT", make_watchdog=Fake)
    assert len(got) == 1
    held.close()


def test_collector_lock_blocks_duplicates(tmp_path):
    first = instance_lock(health.micro_dir(tmp_path) / "collector.lock")
    assert first and instance_lock(health.micro_dir(tmp_path) / "collector.lock") is None
    first.close()


def test_maintenance_alerts_once_and_prunes(tmp_path, monkeypatch):
    monkeypatch.setattr(health.shutil, "disk_usage",
                        lambda p: type("U", (), {"free": 100 * 10**9})())
    alerts, logs = [], []

    class Log:
        def write(self, event, level="info", **kw):
            logs.append(event)

    clock = [time.time()]
    m = supervise.Maintenance(tmp_path, Log(), 30, alerts.append, clock=lambda: clock[0])
    for kind, date in (("depth", "2026-01-01"), ("depth", time.strftime("%Y-%m-%d", time.gmtime())),
                       ("top", "2026-01-01")):
        d = tmp_path / "micro" / kind / "symbol=X" / f"date={date}" / "hour=00"
        d.mkdir(parents=True)
        (d / "part-1.parquet").write_bytes(b"x" * 10)
    clock[0] += health.GRACE_S + 1
    m.tick()
    assert len(alerts) == 1 and "apagado" in alerts[0].detail       # sin latido → aviso
    assert "poda_profundidad" in logs
    assert not (tmp_path / "micro/depth/symbol=X/date=2026-01-01").exists()   # depth viejo
    assert (tmp_path / "micro/top/symbol=X/date=2026-01-01").exists()          # lo demás se queda
    clock[0] += 61
    m.tick()
    assert len(alerts) == 1                                           # no se repite el aviso
    clock[0] += supervise.REALERT_S
    m.tick()
    assert len(alerts) == 2


def test_low_disk_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(health.shutil, "disk_usage",
                        lambda p: type("U", (), {"free": 2 * 10**9})())
    assert any("Disco con 2.0 GB" in m for m in health.problems(tmp_path, NOW))


def test_disk_report_mb_per_day(tmp_path):
    w = HourlyWriter(tmp_path, "trades", "BTCUSDT")
    t = 1_800_000_000_000
    for i in range(50):
        w.add((t + i, i, 100.0, 1.0, False))
    w.flush()
    r = health.disk_report(tmp_path)
    assert r["mb_per_day"]["trades"] > 0 and r["total_mb"] >= 0 and r["free_gb"] > 0


def test_status_endpoint(tmp_path):
    now = [NOW]
    app = FastAPI()
    app.include_router(build_micro_router(tmp_path, lambda: now[0]))
    cli = TestClient(app)
    assert cli.get("/v2/micro/status").json()["state"] == "apagado"
    health.write_heartbeat(tmp_path, {"last_heartbeat": NOW, "last_msg_ms": NOW - 1000,
                                      "started_at": NOW - 5000})
    body = cli.get("/v2/micro/status").json()
    assert body["state"] == "capturando" and body["started_at"] == NOW - 5000


def test_files_are_per_symbol(tmp_path):
    health.write_heartbeat(tmp_path, {"last_heartbeat": NOW}, "BTCUSDT")
    health.write_heartbeat(tmp_path, {"last_heartbeat": NOW - 1}, "ETHUSDT")
    assert (tmp_path / "micro" / "heartbeat.json").exists()
    assert (tmp_path / "micro" / "heartbeat_ETHUSDT.json").exists()
    assert health.read_heartbeat(tmp_path, "ethusdt")["last_heartbeat"] == NOW - 1
    a = instance_lock(tmp_path / "micro" / f"supervisor{health.sfx('BTCUSDT')}.lock")
    b = instance_lock(tmp_path / "micro" / f"supervisor{health.sfx('ETHUSDT')}.lock")
    assert a and b            # dos vigilantes a la vez: uno por símbolo
    a.close()
    b.close()


def test_disk_report_tolerates_part_removed_by_compaction(tmp_path, monkeypatch):
    """Carrera real de T104: la compactación (otro proceso) borra una parte ya listada."""
    monkeypatch.setattr(health.shutil, "disk_usage",
                        lambda p: type("U", (), {"free": 100 * 10**9})())
    d = tmp_path / "micro" / "trades" / "symbol=BTCUSDT" / "date=2026-10-23" / "hour=11"
    d.mkdir(parents=True)
    for name in ("part-1.parquet", "part-2.parquet"):
        (d / name).write_bytes(b"x" * 1000)
    listed = Path.glob

    def racing_glob(self, pattern, *a, **kw):
        found = list(listed(self, pattern, *a, **kw))
        for p in found:
            if p.name == "part-2.parquet":
                p.unlink()                      # entre el listado y el stat()
        return iter(found)

    monkeypatch.setattr(Path, "glob", racing_glob)
    r = health.disk_report(tmp_path)
    assert r["total_mb"] == 0.0 and r["mb_per_day"]["trades"] == round(1000 * 24 / 1e6, 2)
    assert health.problems(tmp_path, NOW)                 # sin latido: avisa, no lanza


class _Log:
    def __init__(self):
        self.rows = []

    def write(self, event, level="info", **kw):
        self.rows.append((event, level, kw))


def test_maintenance_failure_is_logged_not_fatal(tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(supervise.hooks_service, "service_event",
                        lambda comp, what, **kw: events.append((comp, what, kw["status"])))

    def boom(*a, **kw):
        raise FileNotFoundError("part-9.parquet")

    monkeypatch.setattr(health, "problems", boom)
    log, clock = _Log(), [time.time()]
    m = supervise.Maintenance(tmp_path, log, 30, lambda a: None, clock=lambda: clock[0])
    clock[0] += health.GRACE_S + 1
    m.tick()                                              # no mata al vigilante
    fails = [r for r in log.rows if r[0] == "mantenimiento_fallido"]
    assert [(r[1], r[2]["paso"]) for r in fails] == [("error", "check")]
    assert "FileNotFoundError" in fails[0][2]["error"]
    assert "disco" in [r[0] for r in log.rows]            # la poda y el informe siguen
    assert events == [("data.micro_collector", "mantenimiento fallido (check)", "error")]
    clock[0] += 61
    m.tick()                                              # mismo fallo: no se repite el aviso
    assert len([r for r in log.rows if r[0] == "mantenimiento_fallido"]) == 1
    assert len(events) == 1


def test_maintenance_lets_interrupt_through(tmp_path, monkeypatch):
    def stop(*a, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr(health, "problems", stop)
    clock = [time.time()]
    m = supervise.Maintenance(tmp_path, _Log(), 30, lambda a: None, clock=lambda: clock[0])
    clock[0] += health.GRACE_S + 1
    with pytest.raises(KeyboardInterrupt):                # el Watchdog sigue pudiendo pararse
        m.tick()
