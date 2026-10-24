"""T114 · Contrato `TradeProposal` → `RiskDecision`, proyecciones y reglas comunes de la puerta."""

from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import ValidationError

from eim.core import RiskDecision, TradeProposal
from eim.risk import authority
from eim.risk import models as risk_models
from tests.risk.helpers import CFG, H, account, decide, engine, market, plan, proposal


def _p(**kw) -> TradeProposal:
    base = dict(proposal_id="x", source="agents.plan", source_version="1", symbol="BTCUSDT",
                side=1, timeframe="1h", entry=100.0, stop=98.0, data_asof=0, expires_at=10)
    return TradeProposal(**{**base, **kw})


def test_proposal_is_structural_only_and_has_no_order_fields():
    assert _p(stop=101.0).stop == 101.0          # geometría mala: la veta la autoridad, no aquí
    with pytest.raises(ValidationError):
        _p(expires_at=-1)                         # caduca antes del dato que la originó
    with pytest.raises(ValidationError):
        _p(qty=1.0)
    with pytest.raises(ValidationError):
        _p(target_label="objetivo garantizado")   # el objetivo siempre es una estimación
    assert _p(target=104.0).target_label == "estimación"


def test_risk_decision_is_one_contract_for_everyone():
    assert risk_models.RiskDecision is RiskDecision and risk_models.Check is authority.Check
    old = RiskDecision(approved=False, symbol="BTCUSDT", timeframe="1h", plan_id="p", side=1,
                       mode="SIMULADO", asof=0, decided_at=0, config_version="risk_v2",
                       config_sha256="x", account_source="test")
    assert old.proposal is None and old.authority == "risk.engine"   # filas viejas validan
    d = decide(engine()[0])
    back = RiskDecision.model_validate_json(d.model_dump_json())
    assert back == d and back.proposal.source == "agents.plan" and back.exit_mode == "bracket"


def test_plan_proposal_never_expires_before_the_freshness_rule():
    p = plan()
    prop = proposal(p)
    assert prop.expires_at == p.asof + int(CFG.max_plan_age_bars * H)
    eng, _, _ = engine()
    for dt in (-1, 0, 1):
        now = prop.expires_at + dt
        d = decide(eng, p, account(), market(now=now))
        fresh = next(c for c in d.checks if c.rule == "vigencia").ok
        alive = next(c for c in d.checks if c.rule == "caducidad").ok
        assert alive or not fresh, dt              # la caducidad nunca es más estricta


def test_an_expired_signal_is_vetoed_even_if_the_plan_is_fresh():
    eng, _, _ = engine()
    p = plan()
    short = proposal(p).model_copy(update={"expires_at": p.asof + 1})
    d = eng.evaluate(p, account(), market(), proposal=short)
    assert not d.approved and {c.rule for c in d.checks if not c.ok} == {"caducidad"}


def test_requested_max_risk_only_lowers_the_size():
    eng, _, _ = engine()
    p = plan()
    full = decide(eng, p)
    half = eng.evaluate(p, account(), market(), proposal=proposal(p).model_copy(
        update={"max_risk_frac": CFG.risk_per_trade / 2}))
    more = eng.evaluate(p, account(), market(), proposal=proposal(p).model_copy(
        update={"max_risk_frac": CFG.risk_per_trade * 4}))
    assert half.size == pytest.approx(full.size / 2) and more.size == full.size
    assert any("tope pedido por la fuente" in r for r in half.reasons)


def test_registry_is_validated_at_import():
    s = authority.SOURCES["agents.plan"]
    for bad in (replace(s, authorities=("risk.inventada",)), replace(s, status="planeada"),
                replace(s, exit_modes=()), replace(s, exit_modes=("cerrar_por_señal",))):
        with pytest.raises(ValueError):
            authority._validate({**authority.SOURCES, s.id: bad})
    with pytest.raises(ValueError, match="otra clave"):
        authority._validate({"otra": s})


def test_route_reasons_name_what_is_wrong():
    assert authority.route_reason("agents.plan", "risk.engine") is None
    assert "no registrada" in authority.route_reason("nadie", "risk.engine")
    assert "solo informa" in authority.route_reason("bots.squad", "risk.engine")
    assert "planeada" in authority.route_reason("video.intel", "risk.engine")
    assert "decide en" in authority.route_reason("hft.micro", "risk.engine")     # T83: activa
    assert "decide en" in authority.route_reason("agents.plan", "paper.broker")
    assert "modo de salida" in authority.route_reason("agents.plan", "risk.engine", "stop_only")


# --- proyecciones ------------------------------------------------------------------------
def test_paper_idea_projects_onto_the_proposal():
    from tests.paper.helpers import idea
    i = replace(idea(kind="limit", fill_h=2.0), version="abc123")
    p = i.as_proposal()
    assert (p.source, p.proposal_id, p.side, p.entry, p.stop, p.target) == (
        "paper.strategies", i.id, i.side, i.entry, i.sl, i.tp)
    assert p.source_version == i.vid and p.expires_at == i.t + i.fill_ms
    assert p.exit_mode == "sl_tp_time" and p.confidence == i.conf


def test_paper_decision_record_carries_policy_profile_and_granted_exit():
    from eim.core.authority import params_fingerprint
    from eim.paper.policy import AUTHORITY, POLICY_VERSION
    from tests.paper.test_ladder_stop_only_book import P, book, btc
    i = replace(btc(1), origin="vivo")
    st = book("moderado", [i], [(70_000.0, 70_050.0, 69_980.0, 70_030.0)] * 4)
    (d,) = st.decisions
    rec = d.as_record(P["moderado"])
    assert rec.approved and rec.size == st.slots[i.id].qty and rec.authority == AUTHORITY
    assert rec.config_version == POLICY_VERSION and rec.exit_mode == "stop_only"
    assert rec.profile_version == params_fingerprint(P["moderado"])
    assert rec.proposal.proposal_id == i.id and rec.proposal.exit_mode == "sl_tp_time"


def test_bot_signal_projects_onto_the_proposal():
    from eim.core.bots import BotInvalidation
    from tests.agents.bots.test_bots_agent import sig
    s = sig(stance=0.4).model_copy(update={"invalidation": BotInvalidation(
        level=95.0, condition="cierre bajo 95")})
    p = s.as_proposal(price=100.0, ttl_ms=60_000, bar_ms=H)
    assert (p.source, p.side, p.stop, p.entry) == ("bots.squad", 1, 95.0, 100.0)
    assert p.expires_at == s.asof + 60_000 and p.source_version == s.version


def test_arb_plan_and_decision_project_onto_the_contract():
    from tests.execution.arb_helpers import arb_rig
    r = arb_rig()
    d = r.decision()
    p = d.proposal
    assert p.market == "spot_perp" and p.stop is None and p.exit_mode == "arb_rules"
    rec = d.as_record()
    assert rec.approved and rec.size == d.qty and rec.authority == "risk.arb_engine"
    assert rec.proposal == p and rec.plan_id == d.plan.arb_id


def test_copy_decisions_carry_their_proposal_and_subaccount_version():
    from eim.core.authority import params_fingerprint
    from tests.copytrading.copy_helpers import P as COPY_P
    from tests.copytrading.copy_helpers import engine as copy_engine
    from tests.copytrading.copy_helpers import feed
    from tests.copytrading.helpers import T0
    e = copy_engine()
    feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    (d,) = e.risk.decisions or [None]
    assert d is None or d.proposal is not None
    rd = e.risk.check(plan_id="p", coin="ETH", side=1, price=2_500.0, signal_t=T0 + 2_000,
                      now=T0 + 2_300, feed_t=T0 + 2_000, acc=e.account, source="test")
    assert rd.proposal.source == "copy.leaders" and rd.exit_mode == "follow_leader"
    assert rd.profile_version == params_fingerprint(COPY_P)


def test_the_api_decision_shows_its_source(tmp_path):
    from tests.execution.test_api_execution import _app
    from tests.local_client import LocalClient
    from tests.risk.test_api_risk import P as Q
    app, _, reports = _app(tmp_path)
    with LocalClient(app) as c:
        d = c.get("/v2/risk", params=Q).json()["decision"]
    reports.close()
    assert d["proposal"]["source"] == "agents.plan" and d["authority"] == "risk.engine"
    assert d["checks"][0]["rule"] == "fuente" and d["checks"][0]["ok"]


def test_a_broken_projection_never_breaks_the_arb_risk_evaluation(monkeypatch):
    from eim.observability import hooks
    from eim.risk.arb_models import ArbDecision
    from tests.execution.arb_helpers import arb_rig
    monkeypatch.setattr(hooks, "enabled", lambda: True)
    monkeypatch.setattr(ArbDecision, "as_record", lambda self: 1 / 0)
    assert arb_rig().decision().approved                      # observar no rompe lo observado


def test_the_source_cap_keeps_the_event_window_reason():
    eng, _, _ = engine()
    p = plan()
    mkt = market(event_window=True, event_reason="ventana pre-evento: IPC")
    d = eng.evaluate(p, account(), mkt, proposal=proposal(p).model_copy(
        update={"max_risk_frac": CFG.risk_per_trade * CFG.event_size_factor / 2}))
    assert any("tope pedido por la fuente" in r and "IPC" in r for r in d.reasons)
