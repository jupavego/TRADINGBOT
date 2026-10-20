"""T76: marca de evidencia, camino causal y relato de una traza, con un fallo de cada tipo."""

from __future__ import annotations

import threading

import duckdb
import pytest
from fastapi import FastAPI

from eim.api.obs import build_obs_router
from eim.api.security import LocalOnlyMiddleware
from eim.core.mode import Mode
from eim.observability import trace_view as V
from eim.observability.events import Ref, trace_for
from eim.observability.indexer import Indexer
from eim.observability.store import ObsStore
from eim.risk.journal import RiskJournal
from eim.risk.models import Check, RiskDecision
from tests.local_client import LocalClient
from tests.observability.helpers import SYM, T0, TF, ev, write

D = {"symbol": SYM, "timeframe": TF}
HOUR = 3_600_000


def chain(k: int, *, age=5, structure="ok", risk="ok", order=None, plan=True, base=0) -> list:
    """Una vela `k` (traza propia) con el fallo pedido. `base` separa los event_id."""
    tr = trace_for(SYM, TF, T0 - k * HOUR)
    n = base + k * 100
    t = T0 + k * 1000
    snap = Ref(type="snapshot", id=f"snap-{k}", hash="a" * 64)
    out = [
        ev(n + 1, "data_fetch", "data.store", ts=t + 1, run=f"d{k}", trace=tr, source="duckdb",
           coverage=1.0, outputs=[snap], detail={**D, "key": "candles", "age_min": age}),
        ev(n + 2, "signal", "agent.structure", ts=t + 2, run=f"s{k}", trace=tr, status=structure,
           inputs=[snap], detail={**D, "bias": 0.5, "confidence": 0.6,
                                  "warnings": ["datos incompletos"] if structure != "ok" else []}),
        ev(n + 3, "signal", "agent.levels", ts=t + 2, run=f"l{k}", trace=tr, inputs=[snap],
           detail={**D, "bias": -0.3, "confidence": 0.4}),
        ev(n + 4, "synthesis", "synthesis.thesis", ts=t + 3, run=f"y{k}", trace=tr,
           detail={**D, "bias": 0.2, "confidence": 0.5, "agreement": 0.6, "voters": 2}),
    ]
    if plan:
        out.append(ev(n + 5, "plan", "agent.plan", ts=t + 4, run=f"p{k}", trace=tr,
                      outputs=[Ref(type="plan", id=f"plan-{k}")],
                      detail={**D, "side": 1, "entry": 3120.0, "sl": 3100.0, "rr": 2.0}))
        out.append(ev(n + 6, "risk_decision", "risk.engine", ts=t + 5, run=f"r{k}", trace=tr,
                      parent_run_id=f"p{k}", status=risk,
                      outputs=[Ref(type="risk_decision", id=f"plan-{k}@{t + 5}",
                                   params_version="risk_v2")],
                      detail={**D, "approved": risk == "ok", "size": 0.5, "leverage": 2.0,
                              "failed_rules": ["vigencia"] if risk != "ok" else [],
                              "reasons": ["el plan expiró"] if risk != "ok" else []}))
    else:
        out.append(ev(n + 5, "plan", "agent.plan", ts=t + 4, run=f"p{k}", trace=tr,
                      status="no_data", detail={**D, "reason": "sin estructura clara"}))
    if order == "error":
        out.append(ev(n + 7, "order_intent", "execution.service", ts=t + 6, run=f"o{k}",
                      trace=tr, detail={**D, "side": 1}))
        out.append(ev(n + 8, "order_sent", "execution.sim_broker", ts=t + 7, run=f"x{k}",
                      trace=tr, parent_run_id=f"o{k}", status="error",
                      detail={"error": "saldo insuficiente"}))
    return out


@pytest.fixture
def api(tmp_path):
    store = ObsStore(tmp_path / "obs.duckdb")
    spool = tmp_path / "spool"
    ix = Indexer(store, spool)
    con, lock = duckdb.connect(), threading.Lock()
    RiskJournal(con, lock)
    app = FastAPI()
    app.include_router(build_obs_router(store, ix, (con, lock)))
    app.add_middleware(LocalOnlyMiddleware, allowed_hosts=("127.0.0.1", "localhost", "::1"),
                       origins=(), token=None)
    with LocalClient(app) as c:
        yield c, ix, spool, (con, lock)
    store.close()


def load(api, events):
    c, ix, spool, _ = api
    write(spool / "api.20251001.1.jsonl", events)
    ix.run_once()
    return c


def explain(c, k):
    r = c.get(f"/v2/obs/traces/{trace_for(SYM, TF, T0 - k * HOUR)}/explain")
    assert r.status_code == 200
    return r.json()


def test_clean_trace_has_no_findings_and_a_numbered_story(api):
    c = load(api, chain(0))
    j = explain(c, 0)
    assert j["mark"] == "limpia" and j["findings"] == [] and j["causal_path"] == []
    assert [s["n"] for s in j["steps"]] == [1, 2, 3, 4, 5, 6]
    assert "Datos" in j["steps"][0]["title_es"] or j["steps"][0]["kind"] == "data_fetch"
    assert "hace 5 min" in j["steps"][0]["text_es"] and "sin huecos" in j["steps"][0]["text_es"]
    assert "alcista, confianza 0,60" in j["steps"][1]["text_es"]
    assert j["steps"][0]["consumed"]["source"] == "duckdb"
    assert j["steps"][1]["consumed"]["refs"][0]["hash"] == "a" * 64
    assert j["facts"]["decision"]["state"] == "aprobada"
    assert j["facts"]["order"]["state"] == "sin_orden"
    assert j["facts"]["signal"]["bias"] == 0.2


def test_stale_data_marks_the_trace_and_points_at_the_fetch(api):
    c = load(api, chain(1, age=300))
    j = explain(c, 1)
    assert j["mark"] == "con_datos_obsoletos"
    f = j["findings"][0]
    assert f["cause"] == "dato_obsoleto" and f["component_id"] == "data.store"
    assert "300 min" in f["why"] and f["event_id"] in j["causal_path"]


def test_critical_degraded_agent_is_flagged_but_a_plain_one_is_not(api):
    c = load(api, chain(2, structure="degraded"))
    j = explain(c, 2)
    assert j["mark"] == "con_agente_critico_degradado"
    assert j["findings"][0]["why"] == "estado degraded: datos incompletos"
    plain = {"event_id": "e", "component_id": "agent.regime", "kind": "signal",
             "status": "degraded", "ts_utc": 1, "detail": {}}
    f = V.findings([plain], "1h", ("structure",))
    assert f[0]["cause"] == "agente_degradado" and V.mark_of(f) == "limpia"


def test_veto_gives_causal_path_and_matches_the_risk_decision(api):
    c, ix, spool, (con, lock) = api
    k, t = 3, T0 + 3 * 1000
    load(api, chain(k, risk="rejected"))
    RiskJournal(con, lock)(RiskDecision(
        approved=False, symbol=SYM, timeframe=TF, plan_id=f"plan-{k}", side=1, mode=Mode.SIMULADO,
        asof=t, decided_at=t + 5, reasons=("el plan expiró",), config_version="risk_v2",
        config_sha256="x", account_source="test",
        checks=(Check(rule="plan", ok=True, detail="R:R 2.00"),
                Check(rule="vigencia", ok=False, detail="el plan expiró"))))
    j = explain(c, k)
    assert j["mark"] == "limpia"                       # un veto no contamina la evidencia
    assert j["outcome"] == "vetado" and "vetó" in j["headline_es"]
    veto = next(f for f in j["findings"] if f["cause"] == "veto")
    assert "el plan expiró" in veto["why"] and "vigencia" in veto["why"]
    steps = {s["kind"]: s for s in j["steps"]}
    assert steps["risk_decision"]["causal"] and steps["plan"]["causal"]   # padre por parent_run_id
    assert not steps["data_fetch"]["causal"]
    risk = j["facts"]["decision"]["risk"]
    assert j["facts"]["decision"]["state"] == "vetada" and not risk["approved"]
    assert [(x["rule"], x["ok"]) for x in risk["checks"]] == [("plan", True), ("vigencia", False)]
    assert risk["checks"][1]["detail"] == "el plan expiró" and "completo" in risk["source"]
    assert "El riesgo vetó" in steps["risk_decision"]["text_es"]


def test_no_plan_and_order_error(api):
    c = load(api, chain(4, plan=False) + chain(5, order="error"))
    j = explain(c, 4)
    assert j["outcome"] == "sin_plan" and j["findings"][0]["cause"] == "sin_plan"
    assert "sin estructura clara" in j["reasons_es"][0]
    assert j["facts"]["decision"]["state"] == "sin_decision"
    j = explain(c, 5)
    assert j["mark"] == "con_error" and j["facts"]["order"]["state"] == "con_error"
    err = next(f for f in j["findings"] if f["cause"] == "error")
    assert err["why"] == "saldo insuficiente" and err["event_id"] in j["causal_path"]
    # señal, decisión aprobada y orden son tres hechos distintos
    assert j["facts"]["signal"]["bias"] == 0.2 and j["facts"]["decision"]["state"] == "aprobada"


def test_agents_panel_shows_disagreement_with_the_synthesis(api):
    c = load(api, chain(6))
    ag = {a["component_id"]: a for a in explain(c, 6)["agents"]}
    assert ag["agent.structure"]["vs_synthesis"] == 0.3 and not ag["agent.structure"]["opposes"]
    assert ag["agent.levels"]["vs_synthesis"] == -0.5 and ag["agent.levels"]["opposes"]


def test_traces_list_filters_by_mode_and_carries_the_mark(api):
    c = load(api, chain(1, age=300) + chain(0, base=5000))
    items = c.get("/v2/obs/traces", params={"symbol": SYM}).json()["items"]
    assert {i["evidence"] for i in items} == {"con_datos_obsoletos", "limpia"}
    assert c.get("/v2/obs/traces", params={"mode": "SIMULADO"}).json()["total"] == 2
    assert c.get("/v2/obs/traces", params={"mode": "TESTNET"}).json()["total"] == 0


def test_quality_report_matches_a_manual_count(api):
    evs = []
    plan = [(0, {}), (1, {}), (2, {}), (3, {}),                       # 4 limpias
            (4, {"age": 400}), (5, {"age": 400}),                      # 2 datos obsoletos
            (6, {"structure": "degraded"}),                            # 1 crítico degradado
            (7, {"order": "error"}),                                   # 1 con error
            (8, {"risk": "rejected"}), (9, {"plan": False})]           # vetos: no contaminan
    for k, kw in plan:
        evs += chain(k, **kw)
    c = load(api, evs)
    j = c.get("/v2/obs/quality").json()
    assert j["n_decisions"] == 10 and j["n_dirty"] == 4 and j["dirty_share"] == 0.4
    assert j["by_mark"] == {"limpia": 6, "con_datos_obsoletos": 2,
                            "con_agente_critico_degradado": 1, "con_error": 1}
    assert {x["cause"]: x["n"] for x in j["by_cause"]} == {
        "dato_obsoleto": 2, "agente_critico_degradado": 1, "error": 1}
    comp = {x["component_id"]: x["n"] for x in j["by_component"]}
    assert comp == {"data.store": 2, "agent.structure": 1, "execution.sim_broker": 1}
    assert sum(p["n"] for p in j["by_period"]) == 10 and j["n_without_events"] == 0
    assert "no excluye" in j["note_es"]
    only = c.get("/v2/obs/quality", params={"symbol": "ETHUSDT"}).json()
    assert only["n_decisions"] == 0 and only["dirty_share"] is None
    assert c.get("/v2/obs/quality", params={"bucket": "mes"}).status_code == 400


def test_new_routes_are_read_only_and_reject_bad_ids(api):
    c = load(api, chain(0))
    assert c.post("/v2/obs/quality").status_code == 405
    assert c.get("/v2/obs/traces/tr_nada/explain").status_code == 404
