"""T44: agentes nuevos en la síntesis — pesos, correlación, calendario y carril de arbitraje."""
from __future__ import annotations

import pytest

from eim.core import AgentReport
from eim.synthesis import SynthesisParams, synthesize
from eim.synthesis.params import NON_DIRECTIONAL, T44_WEIGHTS, role_of

NEW = ("technical", "smart_money", "literature")


def rep(i: str, bias: float, conf: float = 0.8, status: str = "ok", **metrics) -> AgentReport:
    return AgentReport(agent_id=i, version="1", asof=0, bias=bias, confidence=conf,
                       horizon_bars=10, status=status, metrics=metrics)


def base() -> list[AgentReport]:
    """Agentes existentes: dos alcistas moderados."""
    return [rep("ema", 0.5), rep("structure", 0.4)]


def params(**w) -> SynthesisParams:
    return SynthesisParams(weights={"technical": 0.5, "smart_money": 0.5, **w}, correlation={})


# --- papel y carril propio ---------------------------------------------------------------
def test_roles():
    assert role_of("calendar") == role_of("regime") == "riesgo"
    assert role_of("arbitrage") == "carril" and role_of("plan") == "derivado"
    assert role_of("technical") == role_of("smart_money") == role_of("ema") == "direccional"


@pytest.mark.parametrize("agent", sorted(NON_DIRECTIONAL))
def test_non_directional_never_vote_even_if_forced(agent):
    """Ni vaciando `excluded` ni dándole peso: arbitraje y calendario no suman al sesgo."""
    forced = SynthesisParams(excluded=frozenset(), weights={agent: 5.0}, correlation={})
    ref = synthesize(base(), forced)
    s = synthesize([*base(), rep(agent, 0.9, 1.0)], forced, expected=["ema", "structure", agent])
    assert s.bias == pytest.approx(ref.bias) and agent not in s.contributions
    assert agent not in s.weights and s.confidence == pytest.approx(ref.confidence)


# --- pesos de los agentes nuevos -----------------------------------------------------------
@pytest.mark.parametrize("agent", NEW)
def test_changing_new_agent_weight_moves_synthesis(agent):
    rs = [*base(), rep(agent, -0.9)]
    bias = [synthesize(rs, params(**{agent: w})).bias for w in (0.0, 0.25, 0.5, 1.0, 2.0)]
    assert bias[0] == pytest.approx(synthesize(base(), params()).bias)   # peso 0 = no existe
    assert all(a > b for a, b in zip(bias, bias[1:], strict=False))    # más peso → más bajista
    s = synthesize(rs, params(**{agent: 0.0}))
    assert agent not in s.contributions and s.weights[agent] == 0.0


def test_weight_zero_agent_is_silent():
    """Peso 0: ni contribuye, ni penaliza el acuerdo, ni figura como «sin aporte»."""
    rs = [*base(), rep("technical", -1.0, 1.0)]
    s = synthesize(rs, params(technical=0.0), expected=["ema", "structure", "technical"])
    ref = synthesize(base(), params(technical=0.0))
    assert s.model_dump(exclude={"weights"}) == ref.model_dump(exclude={"weights"})
    assert "technical" not in s.thesis and "desacuerdo" not in s.factors


def test_default_weights_come_from_t44():
    p = SynthesisParams()
    assert {k: p.weights[k] for k in T44_WEIGHTS} == T44_WEIGHTS
    assert set(NEW) | {"bots"} == set(T44_WEIGHTS)   # bots (T57): peso 0 y `excluded`
    assert not ({"technical", "smart_money"} & p.excluded)


# --- penalización por correlación ------------------------------------------------------
def test_correlation_penalty_only_when_correlated_agent_votes():
    p = SynthesisParams(weights={"technical": 1.0}, correlation={"technical": {"ema": 0.6}})
    with_ema = synthesize([rep("ema", 0.5), rep("technical", 0.5)], p)
    assert with_ema.weights["technical"] == pytest.approx(0.4)
    assert "correlación: technical (con ema)" in with_ema.thesis
    ema_off = synthesize([rep("ema", 0, 0, "no_data"), rep("technical", 0.5)], p)
    assert ema_off.weights["technical"] == pytest.approx(1.0)
    no_pen = SynthesisParams(weights={"technical": 1.0}, correlation={})
    rs = [rep("ema", 0.9), rep("technical", -0.5)]
    assert synthesize(rs, p).bias > synthesize(rs, no_pen).bias       # pesa menos el redundante


# --- ausente / degradado -------------------------------------------------------------------
@pytest.mark.parametrize("agent", NEW)
def test_new_agent_absent_or_no_data(agent):
    exp = ["ema", "structure", agent]
    full = synthesize([*base(), rep(agent, 0.45)], params(), expected=exp)
    absent = synthesize(base(), params(), expected=exp)
    nod = synthesize([*base(), rep(agent, 0, 0, "no_data")], params(), expected=exp)
    only = synthesize(base(), params())
    assert absent.bias == pytest.approx(only.bias) and nod.bias == pytest.approx(only.bias)
    assert absent.confidence < only.confidence             # el esperado ausente cuenta 0
    assert absent.confidence == pytest.approx(nod.confidence)
    assert f"Sin aporte: {agent.replace('_', ' ')}" in absent.thesis
    assert full.confidence > absent.confidence


@pytest.mark.parametrize("agent", NEW)
def test_new_agent_degraded_weighs_half(agent):
    rs_ok = [*base(), rep(agent, -0.9)]
    rs_deg = [*base(), rep(agent, -0.9, status="degraded")]
    ok, deg = synthesize(rs_ok, params()), synthesize(rs_deg, params())
    ref = synthesize(base(), params())
    assert ok.bias < deg.bias < ref.bias
    assert abs(deg.contributions[agent]) < abs(ok.contributions[agent])
    assert "Degradados (peso reducido): " + agent.replace("_", " ") in deg.thesis


# --- unanimidad y desacuerdo con los nuevos -----------------------------------------------
def test_unanimity_with_new_agents():
    rs = [rep("ema", 0.6), rep("structure", 0.6), rep("technical", 0.6), rep("smart_money", 0.6)]
    s = synthesize(rs, params())
    assert s.bias == pytest.approx(0.6) and s.agreement == pytest.approx(1.0)
    assert set(s.contributions) == {"ema", "structure", "technical", "smart_money"}
    assert s.factors == {} and s.confidence == pytest.approx(0.8)


def test_disagreement_with_new_agents_penalizes_confidence():
    agree = synthesize([*base(), rep("technical", 0.6), rep("smart_money", 0.5)], params())
    split = synthesize([*base(), rep("technical", -0.8), rep("smart_money", -0.7)], params())
    assert split.factors == {"desacuerdo": 0.5}
    assert split.confidence == pytest.approx(agree.confidence * 0.5)
    assert "smart money, technical (bajista)" in split.thesis
    assert split.agreement < agree.agreement


# --- calendario: reduce la confianza, nunca el sesgo --------------------------------------
EV = {"name": "Consumer Price Index", "t_utc": 0, "impact": "alto"}


@pytest.mark.parametrize("metrics,factor", [
    ({"window": "pre", "window_event": EV, "blackout": False}, 0.75),
    ({"window": "post", "window_event": EV, "blackout": True,
      "blackout_reason": "ventana post-evento de alto impacto: IPC"}, 0.5),
    ({"window": None, "blackout": False}, 1.0),
])
def test_event_window_reduces_confidence_not_bias(metrics, factor):
    ref = synthesize(base(), params())
    s = synthesize([*base(), rep("calendar", 0.0, 0.9, **metrics)], params())
    assert s.bias == pytest.approx(ref.bias) and "calendar" not in s.contributions
    assert s.confidence == pytest.approx(ref.confidence * factor)
    assert s.factors == ({} if factor == 1.0 else {"evento": factor})
    assert ("Calendario:" in s.thesis) == (factor < 1.0)


def test_calendar_without_data_changes_nothing():
    ref = synthesize(base(), params())
    s = synthesize([*base(), rep("calendar", 0, 0, "no_data", window="pre", blackout=True)],
                   params())
    assert s.model_dump() == ref.model_dump()


def test_event_and_disagreement_compose():
    rs = [*base(), rep("technical", -0.9), rep("calendar", 0, 0.9, window="pre",
                                                window_event=EV)]
    s = synthesize(rs, params())
    ref = synthesize([*base(), rep("technical", -0.9)], params())
    assert s.factors == {"desacuerdo": 0.5, "evento": 0.75}
    assert s.confidence == pytest.approx(ref.confidence * 0.75)
