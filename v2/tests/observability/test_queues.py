"""T123: los contadores por frontera llegan al observatorio y la API los sirve con su fuente.

Cada frontera contada sale como `heartbeat` con `detail.queue`, `source` y `coverage`; la API
devuelve el último informe por (frontera, proceso), y una frontera sin informe o con uno viejo
sale `no_data` con su motivo, nunca con ceros inventados.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI

from eim.api.obs import build_obs_router
from eim.observability import emit, queues
from eim.observability.indexer import Indexer
from eim.observability.store import ObsStore
from tests.local_client import LocalClient
from tests.observability.helpers import ev, write


def test_gauge_counts_and_reports_only_the_new_drops_as_degraded():
    g = queues.Gauge(queues.BY_ID["api.cierres"], probe=lambda: 1)
    g.drop(3, "vela 1 sin analizar")
    g.hold(0.25, "espera")
    d = g.detail()
    assert (d["dropped"], d["dropped_new"], d["held"], d["held_s"]) == (3, 3, 1, 0.2)
    assert d["occupancy"] == d["max_occupancy"] == 1 and d["last_cause"] == "espera"
    again = g.detail()
    assert again["dropped"] == 3 and again["dropped_new"] == again["held_new"] == 0


def test_report_emits_one_heartbeat_per_frontier_with_source_and_coverage(tmp_path):
    spool = tmp_path / "spool"
    emit.configure(process="t123", spool_dir=spool, enabled=True)
    try:
        queues.gauge("api.cierres").drop(2, "prueba")
        n = queues.report()
        emit.flush(5.0)
        emit.close()
        lines = [json.loads(x) for f in spool.glob("*.jsonl")
                 for x in f.read_text(encoding="utf-8").splitlines()]
    finally:
        emit.configure(enabled=False)
    got = {e["detail"]["queue"]: e for e in lines if e["kind"] == "heartbeat"}
    assert n == len(got) >= 2 and {"api.cierres", "obs.emisor"} <= set(got)
    e = got["api.cierres"]
    assert e["component_id"] == queues.COMPONENT and e["status"] == "degraded"
    assert e["source"] == "contador en memoria del proceso t123" and e["coverage"] == 1.0
    assert e["detail"]["dropped"] >= 2 and e["detail"]["capacity"] == 1


@pytest.fixture
def api(tmp_path):
    store = ObsStore(tmp_path / "obs.duckdb")
    spool = tmp_path / "spool"
    app = FastAPI()
    ix = Indexer(store, spool)
    app.include_router(build_obs_router(store, ix))
    with LocalClient(app) as c:
        yield c, ix, spool
    store.close()


def _rep(i: int, queue: str, ts: int, process: str = "api", **d):
    detail = {"queue": queue, "capacity": queues.capacity(queue), "policy": "x", "occupancy": 0,
              "max_occupancy": 5, "dropped": 7, "dropped_new": 0, "held": 0, "held_new": 0,
              "held_s": 0.0, "last_cause": "cola llena", "last_ms": ts, "since_ms": ts - 1, **d}
    return ev(i, kind="heartbeat", comp=queues.COMPONENT, ts=ts, process=process, detail=detail,
              source=f"contador en memoria del proceso {process}", coverage=1.0)


def test_queues_endpoint_serves_latest_per_process_and_flags_missing(api):
    c, ix, spool = api
    now = int(time.time() * 1000)
    write(spool / "api.20261107.1.jsonl", [
        _rep(1, "api.cierres", now - 30_000, dropped=1),
        _rep(2, "api.cierres", now - 5_000, dropped=9),          # el último gana
        _rep(3, "agentes.hilos", now - 5_000, process="operation", dropped=2),
        _rep(4, "agentes.hilos", now - 5_000, dropped=1),
        _rep(5, "hft.recepcion", now - 3_600_000, process="hft"),
    ])
    ix.run_once()
    j = c.get("/v2/obs/queues").json()
    assert j["source"].startswith("obs.duckdb") and j["total"] == len(queues.FRONTIERS)
    it = {x["id"]: x for x in j["items"]}
    cie = it["api.cierres"]
    assert not cie["no_data"] and cie["dropped"] == 9 and cie["policy"] == "descartar_viejo"
    p0 = cie["processes"][0]
    assert p0["source"].startswith("contador") and p0["coverage"] == 1.0
    ag = it["agentes.hilos"]
    assert [p["process"] for p in ag["processes"]] == ["api", "operation"] and ag["dropped"] == 3
    assert it["hft.recepcion"]["no_data"] and "sin informe" in it["hft.recepcion"]["no_data_reason"]
    assert it["hft.escritor"]["no_data"] and it["hft.escritor"]["dropped"] is None
    assert it["red.websocket"]["no_data"] and not it["red.websocket"]["measured"]
    one = c.get("/v2/obs/queues", params={"component_id": "api.hub"}).json()["items"]
    assert {x["id"] for x in one} == {"api.cierres", "api.clientes", "agentes.hilos"}
