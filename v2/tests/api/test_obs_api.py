"""T73: API de solo lectura del observatorio — contenido, paginación, seguridad y escala."""

from __future__ import annotations

import statistics
import threading
import time

import duckdb
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from eim.api.config import Settings
from eim.api.main import create_app
from eim.api.obs import build_obs_router
from eim.api.security import LocalOnlyMiddleware
from eim.execution.sim_ledger import SimLedger
from eim.observability import thresholds as T
from eim.observability.events import trace_for
from eim.observability.indexer import Indexer
from eim.observability.store import ObsStore
from eim.risk.journal import RiskJournal
from tests.local_client import LocalClient
from tests.observability.helpers import CLOSE, SYM, T0, TF, candle_trace, ev, write


@pytest.fixture
def parts(tmp_path):
    store = ObsStore(tmp_path / "obs.duckdb")
    spool = tmp_path / "spool"
    ix = Indexer(store, spool)
    con, lock = duckdb.connect(), threading.Lock()
    RiskJournal(con, lock)
    SimLedger(con, lock)
    con.execute("INSERT INTO sim_trades VALUES ('st-1', 'BTCUSDT', '1h', ?, 'CERRADA', '{}')", [T0])
    app = FastAPI()
    app.include_router(build_obs_router(store, ix, (con, lock)))
    app.add_middleware(LocalOnlyMiddleware, allowed_hosts=("127.0.0.1", "localhost", "::1"),
                       origins=(), token=None)
    write(spool / "api.20251001.1.jsonl", candle_trace())
    ix.run_once()
    with LocalClient(app) as c:
        yield c, store, ix, spool
    store.close()


def test_every_response_declares_source_asof_and_lag(parts):
    c, *_ = parts
    for path in ("components", "graph", "runs", "events", "traces", "health"):
        j = c.get(f"/v2/obs/{path}").json()
        assert j["source"].startswith("obs.duckdb") and j["asof"] > 0, path
        assert j["last_event_age_s"] >= 0 and j["index_lag_s"] is not None, path
        assert j["last_event_ms"] == T0 + 10


def test_trace_endpoint_rebuilds_the_candle_in_order(parts):
    c, *_ = parts
    tr = trace_for(SYM, TF, CLOSE)
    j = c.get(f"/v2/obs/traces/{tr}").json()
    kinds = [e["kind"] for e in j["events"]]
    assert kinds == ["run_start", "data_fetch", "signal", "signal", "synthesis", "plan",
                     "risk_decision", "order_intent", "order_sent", "fill", "run_end"]
    assert [e["ts_utc"] for e in j["events"]] == sorted(e["ts_utc"] for e in j["events"])
    assert j["decision"]["outcome"] == "ejecutada" and not j["partial"]
    fetch = next(e for e in j["events"] if e["kind"] == "data_fetch")
    assert fetch["outputs"][0]["hash"] == "h" * 64 and fetch["source"] == "duckdb"
    assert {e["process"] for e in j["events"]} == {"operation", "api"}
    assert j["runs"][0]["run_id"] == "cyc"
    # enlaces a los libros existentes: solo existencia, no copia
    assert j["resolved"]["sim_trade"] == [
        {"ref": "st-1", "found": True, "id": "st-1", "symbol": "BTCUSDT", "timeframe": "1h",
         "state": "CERRADA", "t": T0}]
    assert j["resolved"]["risk_decision"][0]["found"] is False      # rd-1 no está en el libro
    assert j["resolved"]["agent_report"][0]["found"] is False


def test_unknown_or_malformed_trace(parts):
    c, *_ = parts
    assert c.get("/v2/obs/traces/tr_inexistente").status_code == 404
    assert c.get("/v2/obs/traces/a b;drop").status_code in (400, 404)
    assert c.get("/v2/obs/events", params={"trace_id": "x' OR 1=1 --"}).status_code == 400


def test_filters_and_pagination(parts):
    c, store, ix, spool = parts
    write(spool / "api.20251001.2.jsonl", [ev(100 + i, "heartbeat", "operation.supervisor",
                                              run="hb", process="operation") for i in range(30)])
    ix.run_once()
    p1 = c.get("/v2/obs/events", params={"kind": "heartbeat", "limit": 10}).json()
    p2 = c.get("/v2/obs/events", params={"kind": "heartbeat", "limit": 10, "offset": 10}).json()
    assert p1["total"] == 30 and len(p1["items"]) == 10 and p1["limit"] == 10
    assert not {e["event_id"] for e in p1["items"]} & {e["event_id"] for e in p2["items"]}
    assert [e["ts_utc"] for e in p1["items"]] == sorted((e["ts_utc"] for e in p1["items"]),
                                                        reverse=True)
    assert c.get("/v2/obs/events", params={"limit": T.PAGE_MAX + 1}).status_code == 422
    assert c.get("/v2/obs/events", params={"offset": -1}).status_code == 422
    r = c.get("/v2/obs/runs", params={"component_id": "operation.cycle"}).json()
    assert r["total"] == 1 and r["items"][0]["status"] == "ok"
    t = c.get("/v2/obs/traces", params={"symbol": SYM, "outcome": "ejecutada"}).json()
    assert t["total"] == 1 and t["items"][0]["links"]["sim_trade"] == ["st-1"]
    assert c.get("/v2/obs/traces", params={"outcome": "vetado"}).json()["total"] == 0


def test_components_report_no_data_and_graph_matches_catalog(parts):
    c, *_ = parts
    j = c.get("/v2/obs/components", params={"stage": "riesgo"}).json()
    ids = {x["id"]: x for x in j["items"]}
    assert ids["risk.engine"]["n_events"] == 1 and ids["risk.engine"]["last_status"] == "ok"
    # un componente construido que nunca emitió se marca «sin datos» (no se inventa actividad)
    quiet = next(x for x in c.get("/v2/obs/components").json()["items"]
                 if x["built"] == "construido" and x["n_events"] == 0)
    assert quiet["no_data"] is True
    planned = [x for x in c.get("/v2/obs/components", params={"built": "planeado"}).json()["items"]]
    assert planned and not any(x["no_data"] for x in planned)
    g = c.get("/v2/obs/graph").json()
    assert len(g["nodes"]) > 50 and g["edges"] and len(g["stages"]) == 7


def test_health_flags_stalled_indexer_and_corruption(parts):
    c, store, ix, spool = parts
    h = c.get("/v2/obs/health").json()
    assert h["ok"] is True and h["counts"]["events"] == 11 and h["corrupt_lines"] == 0
    with (spool / "api.20251001.1.jsonl").open("ab") as f:
        f.write(b"basura\n")
    ix.run_once()
    assert c.get("/v2/obs/health").json()["corrupt_lines"] == 1
    ix.last_pass_ms -= (T.INDEX_LAG_S_MAX + 30) * 1000       # el indexador dejó de pasar
    h = c.get("/v2/obs/health").json()
    assert h["ok"] is False and any("sin pasar" in p for p in h["problems"])


def test_no_mutating_methods_and_same_guards_as_the_rest(parts):
    c, *_ = parts
    for m in ("post", "put", "patch", "delete"):
        assert getattr(c, m)("/v2/obs/events").status_code == 405
    assert c.get("/v2/obs/health", headers={"host": "evil.example:8000"}).status_code == 400
    with LocalClient(c.app, client=("192.168.1.20", 4000)) as remote:
        assert remote.get("/v2/obs/health").status_code == 403
    with TestClient(c.app) as stranger:                      # Host «testserver»
        assert stranger.get("/v2/obs/health").status_code == 400


def test_full_app_exposes_only_gets_and_serves_the_observatory(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    paths = {p: m for p, m in app.openapi()["paths"].items() if p.startswith("/v2/obs")}
    assert len(paths) == 7 and all(set(m) == {"get"} for m in paths.values())
    write(tmp_path / "obs" / "spool" / "api.20251001.1.jsonl", candle_trace())
    app.state.obs_indexer.run_once()
    with LocalClient(app) as c:
        assert c.get("/v2/obs/health").json()["counts"]["events"] == 11
        assert c.get("/v2/obs/events", headers={"host": "evil.example"}).status_code == 400


def test_queries_over_100k_events_stay_within_the_threshold(tmp_path):
    store = ObsStore(tmp_path / "obs.duckdb")
    spool = tmp_path / "spool"
    ix = Indexer(store, spool)
    ix._last_purge_ms = 2**62
    comps = ["agent.structure", "agent.levels", "risk.engine", "data.snapshot", "synthesis.thesis"]
    n = 100_000
    write(spool / "big.20251001.1.jsonl", (
        ev(i, "signal", comps[i % 5], ts=T0 - 3_000_000 + i * 20, run=f"r{i // 50}",
           trace=trace_for(SYM, TF, T0 + (i // 20) * 3_600_000), detail={"symbol": SYM, "i": i})
        for i in range(n)))
    t0 = time.perf_counter()
    assert ix.run_once()["new"] == n
    index_s = time.perf_counter() - t0
    assert store.counts()["events"] == n and store.counts()["decisions"] == n // 20
    assert ix.run_once()["new"] == 0                         # idempotente también a esta escala
    app = FastAPI()
    app.include_router(build_obs_router(store, ix))
    probe = trace_for(SYM, TF, T0 + 500 * 3_600_000)
    queries = [("/v2/obs/events", {"limit": 100}),
               ("/v2/obs/events", {"component_id": "risk.engine", "limit": 100}),
               ("/v2/obs/events", {"trace_id": probe}),
               ("/v2/obs/events", {"kind": "signal", "since": T0 - 1_000_000, "limit": 100}),
               ("/v2/obs/runs", {"limit": 100}), ("/v2/obs/traces", {"limit": 100}),
               (f"/v2/obs/traces/{probe}", {}), ("/v2/obs/components", {}),
               ("/v2/obs/graph", {}), ("/v2/obs/health", {})]
    with TestClient(app) as c:
        for path, params in queries:
            lat = []
            for _ in range(20):
                t = time.perf_counter()
                assert c.get(path, params=params).status_code == 200
                lat.append((time.perf_counter() - t) * 1000)
            p95 = statistics.quantiles(lat, n=20)[-1]
            assert p95 <= T.QUERY_P95_MS_MAX, f"{path} {params}: p95 {p95:.0f} ms"
    assert index_s < 60, f"indexar 100 000 eventos tardó {index_s:.0f} s"
    store.close()


def test_graph_carries_glossary_mode_and_deviation_keys(parts):
    c, *_ = parts
    j = c.get("/v2/obs/graph").json()
    assert "veto" in j["glossary"] and set(j["stage_explain_es"]) == set(j["stages"])
    assert set(j["deviations"]) == {"undeclared", "unseen"}
    assert isinstance(j["observed"], list) and "mode" in j
