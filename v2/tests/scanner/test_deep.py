"""T94 — activación selectiva y oportunidades trazables (sin red, agentes de prueba).

Elegibilidad respetada (el no elegible no corre y queda con su motivo), oportunidad reproducible
a partir de su hash, puntuaciones separadas y ningún camino hacia riesgo ni ejecución.
"""

from __future__ import annotations

import pytest

from eim.agents.capabilities import CAPABILITIES
from eim.core import AgentReport
from eim.core.opportunity import STATUS, Opportunity
from eim.scanner import deep
from tests.scanner._helpers import DAY, T0, candles, perp

ASOF = T0 + 101 * DAY + 3_600_000
CUT = T0 + 101 * DAY


class FakeAgent:
    """Agente de prueba con el id de uno real (la elegibilidad mira su ficha por id)."""

    def __init__(self, agent_id: str, bias: float, conf: float = 0.8, version: str = "9.9"):
        self.id, self.version, self.bias, self.conf = agent_id, version, bias, conf
        self.requires = CAPABILITIES[agent_id].all_requires
        self.calls = 0

    def run(self, snap):
        self.calls += 1
        return AgentReport(agent_id=self.id, version=self.version, asof=snap.asof,
                           bias=self.bias, confidence=self.conf, horizon_bars=12,
                           evidence=[f"{len(snap.candles)} velas"])


def agents(bias: float = 0.6):
    return [FakeAgent("ema", bias), FakeAgent("structure", bias * 0.8),
            FakeAgent("microstructure", 1.0), FakeAgent("derivatives", -1.0)]


def run(cs=None, ags=None, **kw):
    return deep.analyze(perp("AUSDT"), cs or candles(150, seed=1), ags or agents(), asof=ASOF,
                        timeframe="1d", cut=CUT, run_id="barrido-1", source="prueba", **kw)


def test_only_eligible_agents_run_and_the_rest_say_why():
    ags = agents()
    r = run(ags=ags)
    assert [a["agent_id"] for a in r.ran] == ["ema", "structure"]
    why = {s["agent_id"]: s["reason"] for s in r.skipped}
    assert "marco no soportado" in why["microstructure"]
    assert "interés abierto" in why["derivatives"]
    assert ags[2].calls == 0 and ags[3].calls == 0          # nunca se llamó a un no elegible
    assert ags[0].calls == 1 and ags[1].calls == 1


def test_opportunity_is_candidate_traceable_and_scored_apart():
    r = run(screen={"quality": 0.9, "score": 0.7, "rank": 1}, spread_bps=2.0)
    o = Opportunity.model_validate(r.opportunity)
    assert o.status == STATUS and o.mode == "ANALISIS" and o.side == "largo"
    assert o.input_hash == r.input_hash and o.input_ref.n_bars == 150 and o.input_ref.cut == CUT
    assert {a.agent_id for a in o.agents} == {"ema", "structure"}
    assert all(a.version == "9.9" for a in o.agents)
    assert set(o.versions) >= {"deep", "opportunity", "scoring", "capabilities"}
    s = o.scores
    assert 0 <= s.signal_quality <= 1 and 0 <= s.viability <= 1 and 0 <= s.risk_cost <= 1
    assert s.components["spread_bps"] == 2.0 and s.components["data_quality"] == 0.9
    assert set(o.forecast["scenarios"]) == {"bull", "neutral", "bear"}
    assert o.valid_until == CUT + DAY and o.horizon_ms == o.horizon_bars * DAY


def test_same_data_same_id_and_figures_other_data_other_id():
    a, b = run(), run()
    assert a.opportunity == b.opportunity
    c = run(cs=candles(150, seed=2))
    assert c.input_hash != a.input_hash
    assert c.opportunity["opportunity_id"] != a.opportunity["opportunity_id"]
    d = run(ags=[FakeAgent("ema", 0.6, version="10.0"), FakeAgent("structure", 0.48)])
    assert d.opportunity["opportunity_id"] != a.opportunity["opportunity_id"]   # versión


def test_verify_reproduces_from_the_hash():
    cs = candles(150, seed=1)
    opp = run(cs=cs).opportunity
    out = deep.verify(opp, cs, agents(), inst=perp("AUSDT"))
    assert out["hash_ok"] and out["reproduced"]
    touched = [*cs[:-1], cs[-1].model_copy(update={"c": cs[-1].c * 1.0001,
                                                    "h": cs[-1].h * 1.0001})]
    assert not deep.verify(opp, touched)["hash_ok"]


def test_neutral_synthesis_gives_no_opportunity_and_says_why():
    r = run(ags=[FakeAgent("ema", 0.02), FakeAgent("structure", -0.01)])
    assert r.opportunity is None and "síntesis neutral" in r.reason
    assert r.synthesis is not None and r.forecast is not None


def test_no_eligible_agent_is_said():
    r = run(ags=[FakeAgent("microstructure", 1.0)])
    assert r.opportunity is None and r.reason == "ningún agente elegible" and not r.ran


def test_short_side_and_no_spread_is_declared():
    r = run(ags=agents(-0.7))
    o = r.opportunity
    assert o["side"] == "corto"
    assert o["scores"]["components"]["spread"] is None
    assert any("spread sin medir" in n for n in o["scores"]["notes"])


def test_the_opportunity_cannot_become_an_order():
    o = Opportunity.model_validate(run().opportunity)
    for attr in ("as_proposal", "qty", "size", "notional", "leverage", "account"):
        assert not hasattr(o, attr)
    with pytest.raises(ValueError):
        Opportunity.model_validate({**o.model_dump(), "status": "validada"})
    with pytest.raises(ValueError):
        Opportunity.model_validate({**o.model_dump(), "mode": "TESTNET"})
