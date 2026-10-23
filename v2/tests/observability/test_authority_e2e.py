"""T114 · Una aprobación y un rechazo, visibles en el Observatorio de punta a punta.

Emisor real → spool → indexador → `/v2/obs/traces/{id}/explain` (T76), para dos fuentes: el plan
de los agentes dentro del ciclo (traza de su vela) y el bróker simulado con ideas en vivo (una
traza por idea y perfil). Cada decisión dice su fuente, su versión, los datos usados, la
autoridad que decidió y el resultado; reemitir (recálculo o reinicio) no duplica nada.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi import FastAPI

import eim.observability.emit as E
from eim.api.obs import build_obs_router
from eim.execution.gateway import OrderGateway
from eim.observability.emit import span
from eim.observability.events import proposal_trace, trace_for
from eim.observability.indexer import Indexer
from eim.observability.store import ObsStore
from eim.paper.authority_obs import DecisionEmitter
from tests.local_client import LocalClient
from tests.paper.test_ladder_stop_only_book import E as PX
from tests.paper.test_ladder_stop_only_book import book, btc, mirror
from tests.risk.helpers import NOW, H, decide, engine, plan
from tests.risk.test_gate import FakeBroker


@pytest.fixture
def obs(spool, tmp_path):
    store = ObsStore(tmp_path / "obs.duckdb")
    ix = Indexer(store, spool)
    ix._last_purge_ms = 2**62                    # sin purga: los instantes de prueba son viejos
    app = FastAPI()
    app.include_router(build_obs_router(store, ix))

    def explain(trace_id: str) -> dict:
        E.flush()
        ix.run_once()
        with LocalClient(app) as c:
            r = c.get(f"/v2/obs/traces/{trace_id}/explain")
        assert r.status_code == 200, r.text
        return r.json()

    yield explain, store
    store.close()


def _step(j: dict, kind: str) -> dict:
    return next(s for s in j["steps"] if s["kind"] == kind)


def test_agents_plan_approval_and_veto_end_to_end(obs):
    explain, _ = obs
    eng, _, _ = engine()
    gw = OrderGateway(eng, FakeBroker())
    ok, no = plan(plan_id="plan:ok"), plan(plan_id="plan:no", rr=0.5, asof=NOW - H - 300_000)
    for p in (ok, no):
        with span("operation.cycle", trace_id=trace_for(p.symbol, p.timeframe, p.asof)):
            d = decide(eng, p)
            if d.approved:
                gw.submit(d, NOW)
    j = explain(trace_for(ok.symbol, ok.timeframe, ok.asof))
    assert j["facts"]["decision"]["state"] == "aprobada"
    assert j["facts"]["order"]["state"] == "enviada"
    risk = _step(j, "risk_decision")
    assert "aprobó la propuesta de agents.plan" in risk["text_es"]
    refs = {r["type"]: r for r in risk["consumed"]["refs"]}
    assert refs["proposal"]["id"] == "plan:ok" and refs["proposal"]["params_version"] == "test"
    assert refs["data"]["id"] == f"{ok.symbol}:{ok.timeframe}:{ok.asof}"
    v = explain(trace_for(no.symbol, no.timeframe, no.asof))
    assert v["facts"]["decision"]["state"] == "vetada"
    assert v["facts"]["order"]["state"] == "sin_orden"
    assert "vetó la propuesta de agents.plan" in _step(v, "risk_decision")["text_es"]


ROWS = [(PX, PX + 50, PX - 20, PX + 30)] + [(PX + 30, PX + 60, PX + 10, PX + 40)] * 8


def _live_book():
    """Conservador (sin cobertura): una larga en vivo entra; la corta contraria se rechaza."""
    a = replace(btc(1, strategy="a"), origin="vivo")
    b = replace(btc(-1, t=a.t + H, strategy="b"), entry=mirror(ROWS, 1).o[4], origin="vivo")
    b = replace(b, sl=b.entry + 1400, tp=b.entry - 2200)
    return book("conservador", [a, b], ROWS), a, b


def test_paper_broker_approval_and_rejection_end_to_end(obs):
    explain, store = obs
    st, a, b = _live_book()
    assert a.id in st.slots and b.id not in st.slots
    n = DecisionEmitter().emit_books({"conservador": st})
    assert n == 5                                 # 2 por decisión + el llenado de la abierta
    ja = explain(proposal_trace(a.as_proposal(), scope="conservador"))
    assert ja["facts"]["decision"]["state"] == "aprobada"
    assert ja["facts"]["order"]["state"] == "ejecutada"
    assert [s["kind"] for s in ja["steps"]] == ["plan", "risk_decision", "fill"]
    assert "La estrategia a@1h propuso una operación larga" in ja["steps"][0]["text_es"]
    risk = ja["steps"][1]
    assert "aprobó la propuesta de paper.strategies" in risk["text_es"]
    assert "Decidió: Bróker simulado" in risk["text_es"]
    jb = explain(proposal_trace(b.as_proposal(), scope="conservador"))
    assert jb["facts"]["decision"]["state"] == "vetada"
    assert "lado opuesto" in _step(jb, "risk_decision")["text_es"]
    before = store.scalar("SELECT count(*) FROM events")
    DecisionEmitter().emit_books({"conservador": st})       # «reinicio»: mismo hecho, mismo id
    explain(proposal_trace(a.as_proposal(), scope="conservador"))
    assert store.scalar("SELECT count(*) FROM events") == before


def test_backtest_ideas_are_not_emitted(obs):
    st = book("conservador", [btc(1)], ROWS)                 # origen «backtest»
    assert st.decisions == [] and DecisionEmitter().emit_books({"c": st}) == 0


def test_a_dropped_event_is_retried_on_the_next_recompute(obs, monkeypatch):
    import eim.paper.authority_obs as A
    explain, _ = obs
    st, a, _ = _live_book()
    em, real = DecisionEmitter(), A.emit
    monkeypatch.setattr(A, "emit", lambda *a, **k: False)        # cola llena: se descarta
    assert em.emit_books({"conservador": st}) == 0
    monkeypatch.setattr(A, "emit", real)
    assert em.emit_books({"conservador": st}) == 5               # el siguiente cálculo reintenta
    assert explain(proposal_trace(a.as_proposal(), scope="conservador"))["facts"][
        "decision"]["state"] == "aprobada"
