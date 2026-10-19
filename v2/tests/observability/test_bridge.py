"""T73: puentes de solo lectura con latidos, alertas y riesgo (sin tocar esos módulos)."""

from __future__ import annotations

import json
import threading
import time

import duckdb

from eim.core.mode import Mode
from eim.observability.bridge import alerts_bridge, heartbeat_bridge, risk_bridge
from eim.observability.events import trace_for
from eim.observability.indexer import Indexer
from eim.observability.store import ObsStore
from eim.operation.alerts import Alert, AlertCenter
from eim.risk.journal import RiskJournal
from eim.risk.models import RiskDecision

NOW = int(time.time() * 1000)


def _decision(plan_id: str, approved: bool, decided: int, reasons=()) -> RiskDecision:
    return RiskDecision(approved=approved, symbol="BTCUSDT", timeframe="1h", plan_id=plan_id,
                        side=1, mode=Mode.SIMULADO, asof=NOW - 3_600_000, decided_at=decided,
                        size=1.0, reasons=tuple(reasons), config_version="c1",
                        config_sha256="0" * 64, account_source="test")


def _indexer(tmp_path, *bridges):
    store = ObsStore(tmp_path / "obs.duckdb")
    return store, Indexer(store, tmp_path / "spool", bridges=bridges)


def test_heartbeat_files_become_events_once(tmp_path):
    (tmp_path / "operation").mkdir()
    hb = tmp_path / "operation" / "heartbeat.json"
    hb.write_text(json.dumps({"last_heartbeat": NOW, "pid": 1, "state": "operando",
                              "mode": "SIMULADO", "cycles": 7, "consecutive_failures": 0}))
    (tmp_path / "paper").mkdir()
    (tmp_path / "paper" / "heartbeat.json").write_text(
        json.dumps({"last_tick": NOW // 1000, "saved": 3, "error": "sin red"}))
    store, ix = _indexer(tmp_path, ("heartbeat", heartbeat_bridge(tmp_path)))
    assert ix.run_once()["bridge"] == 2
    assert ix.run_once()["bridge"] == 0                        # mismo latido: ni uno más
    rows = {r["component_id"]: r for r in store.query("SELECT * FROM events")}
    assert rows["operation.supervisor"]["kind"] == "heartbeat"
    assert rows["operation.supervisor"]["mode"] == "SIMULADO"
    assert rows["paper.broker"]["status"] == "degraded"        # el latido trae un error
    assert rows["paper.broker"]["ts_utc"] == (NOW // 1000) * 1000   # segundos → ms
    hb.write_text(json.dumps({"last_heartbeat": NOW + 60_000, "state": "operando"}))
    assert ix.run_once()["bridge"] == 1                        # latido nuevo = evento nuevo
    assert store.scalar("SELECT count(*) FROM events WHERE kind = 'heartbeat'") == 3


def test_broken_or_missing_heartbeat_is_ignored(tmp_path):
    (tmp_path / "leaders").mkdir()
    (tmp_path / "leaders" / "heartbeat.json").write_text("{no es json")
    store, ix = _indexer(tmp_path, ("heartbeat", heartbeat_bridge(tmp_path)))
    assert ix.run_once()["bridge"] == 0 and ix.last_error is None


def test_alerts_and_risk_bridge_read_existing_tables(tmp_path):
    con, lock = duckdb.connect(), threading.Lock()
    center = AlertCenter(con, lock)
    center.emit(Alert(NOW, "kill_switch", "critical", "Kill-switch activado", key="kill"))
    center.emit(Alert(NOW + 1, "servicio", "info", "Todo en orden", key="svc"))
    journal = RiskJournal(con, lock)
    journal(_decision("p1", True, NOW))
    journal(_decision("p2", False, NOW + 5, reasons=["riesgo > 1 %"]))
    store, ix = _indexer(tmp_path, ("alerts", alerts_bridge(con, lock)),
                         ("risk", risk_bridge(con, lock)))
    assert ix.run_once()["bridge"] == 4
    assert ix.run_once()["bridge"] == 0                        # idempotente (marca de agua)
    al = store.query("SELECT * FROM events WHERE kind = 'alert' ORDER BY ts_utc")
    assert [a["status"] for a in al] == ["error", "ok"]
    assert al[0]["component_id"] == "operation.alerts"
    rk = store.query("SELECT * FROM events WHERE kind = 'risk_decision' ORDER BY ts_utc")
    assert [r["status"] for r in rk] == ["ok", "rejected"]
    tr = trace_for("BTCUSDT", "1h", NOW - 3_600_000)
    assert all(r["trace_id"] == tr for r in rk)
    d = store.query("SELECT * FROM decisions WHERE trace_id = ?", [tr])[0]
    assert d["outcome"] == "vetado" and d["risk_status"] == "rejected"
    refs = store.query("SELECT type FROM refs WHERE type = 'risk_decision'")
    assert len(refs) == 2
    # re-evaluar el mismo plan con otro resultado = otro evento; el mismo = ninguno
    journal(_decision("p1", True, NOW + 100))
    journal(_decision("p1", False, NOW + 200, reasons=["ahora vetado"]))
    assert ix.run_once()["bridge"] == 1


def test_bridges_tolerate_missing_tables(tmp_path):
    con, lock = duckdb.connect(), threading.Lock()
    store, ix = _indexer(tmp_path, ("alerts", alerts_bridge(con, lock)),
                         ("risk", risk_bridge(con, lock)))
    assert ix.run_once()["bridge"] == 0 and ix.last_error is None
