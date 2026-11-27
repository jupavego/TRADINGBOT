"""T102 — `/v2/scanner/health` y `/v2/scanner/trace/{id}`: solo lectura, modo visible, frescura con
la hora de la petición y las candidatas en sombra aparte."""

from __future__ import annotations

import json

from fastapi import FastAPI

from eim.api.scanner import build_scanner_router
from eim.data.scanner_view import write_view
from eim.scanner import health_service as HS
from tests.local_client import LocalClient
from tests.scanner._t102 import STATUS, iid, make_view


def _app(path) -> FastAPI:
    app = FastAPI()
    app.include_router(build_scanner_router(path))
    return app


def _world(tmp_path, view):
    (tmp_path / "scanner").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scanner" / "status.json").write_text(json.dumps(STATUS), encoding="utf-8")
    write_view(tmp_path, view)


def test_health_without_anything_is_no_data_never_ok(tmp_path):
    with LocalClient(_app(tmp_path)) as c:
        h = c.get("/v2/scanner/health").json()
    assert h["mode"] == "ANALISIS" and h["overall"] == "sin_datos" and "note" in h
    assert next(x for x in h["classes"] if x["asset_class"] == "crypto")["state"] == "sin_datos"


def test_health_recomputes_freshness_at_request_time(tmp_path):
    _world(tmp_path, make_view(now=1_000))               # vista publicada hace mucho
    with LocalClient(_app(tmp_path)) as c:
        h = c.get("/v2/scanner/health").json()
    assert h["overall"] == "obsoleto" and h["view"]["state"] == "obsoleto"


def test_health_merges_the_saved_review(tmp_path):
    import time

    now = int(time.time() * 1000)
    _world(tmp_path, make_view(now=now))
    HS.check(tmp_path, now=now, sinks=[], emit_events=False,
             excl_by_class={"crypto": {"liquidez": 2}})
    with LocalClient(_app(tmp_path)) as c:
        h = c.get("/v2/scanner/health").json()
    crypto = next(x for x in h["classes"] if x["asset_class"] == "crypto")
    assert h["overall"] == "ok" and crypto["coverage"] == 0.75
    assert h["rollout"]["units"]["class:crypto"]["level"] == "alerta"
    assert h["checked_at"] == now and h["alerts_active"] == {}


def test_trace_follows_a_candidate_and_404s_otherwise(tmp_path):
    _world(tmp_path, make_view())
    with LocalClient(_app(tmp_path)) as c:
        t = c.get(f"/v2/scanner/trace/{iid('crypto', 'CRY0USDT')}").json()
        assert t["mode"] == "ANALISIS" and t["status_label"] == "candidata, no validada"
        assert t["steps"][0]["key"] == "dato" and t["steps"][-1]["key"] == "decision"
        assert c.get("/v2/scanner/trace/crypto.binance.usdm.NOPE").status_code == 404


def test_candidates_of_a_deactivated_class_go_to_shadow(tmp_path):
    _world(tmp_path, make_view())
    (tmp_path / "scanner" / "rollout.json").write_text(json.dumps({"units": {
        "class:crypto": {"kind": "class", "id": "crypto", "level": "alerta", "active": False,
                         "reason": "sin datos dos veces"}}}), encoding="utf-8")
    with LocalClient(_app(tmp_path)) as c:
        o = c.get("/v2/scanner/opportunities").json()
        assert o["opportunities"] == [] and len(o["shadow"]) == 3
        assert o["shadow"][0]["reason"].startswith("clase desactivada")
        assert len(c.get("/v2/scanner/opportunities?include_shadow=true").json()[
            "opportunities"]) == 3


def test_no_new_method_changes_state(tmp_path):
    app = _app(tmp_path)
    methods = {m for r in app.routes for m in getattr(r, "methods", set())}
    assert methods <= {"GET", "HEAD"}
