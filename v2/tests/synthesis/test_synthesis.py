"""Síntesis v1: unanimidad, empate, degradado, ausente, pesos y deriva."""
from __future__ import annotations

import pytest

from eim.core import AgentReport
from eim.synthesis import SynthesisParams, drift_of, synthesize


def rep(i: str, bias: float, conf: float = 0.8, status: str = "ok") -> AgentReport:
    return AgentReport(agent_id=i, version="1", asof=0, bias=bias, confidence=conf,
                       horizon_bars=10, status=status)


def test_unanimity():
    s = synthesize([rep("a", 0.6), rep("b", 0.6), rep("c", 0.6)])
    assert s.bias == pytest.approx(0.6) and s.agreement == pytest.approx(1.0)
    assert s.confidence == pytest.approx(0.8) and "alcista" in s.thesis
    assert sum(s.contributions.values()) == pytest.approx(s.bias)


def test_tie_is_neutral_with_penalty():
    s = synthesize([rep("a", 0.8), rep("b", -0.8)])
    assert s.bias == pytest.approx(0) and s.agreement < 0.5
    assert s.confidence == pytest.approx(0.8 * 0.5) and "Desacuerdo" in s.thesis
    assert "neutral" in s.thesis


def test_degraded_weighs_less():
    full = synthesize([rep("a", 0.8), rep("b", -0.8)])
    deg = synthesize([rep("a", 0.8), rep("b", -0.8, status="degraded")])
    assert deg.bias > full.bias and "Degradados" in deg.thesis


def test_missing_and_no_data_lower_confidence():
    base = synthesize([rep("a", 0.5), rep("b", 0.5)])
    miss = synthesize([rep("a", 0.5), rep("b", 0.5)], expected=["a", "b", "c"])
    nod = synthesize([rep("a", 0.5), rep("b", 0.5), rep("c", 0, 0, "no_data")])
    assert miss.confidence < base.confidence and nod.confidence == pytest.approx(miss.confidence)
    assert "Sin aporte: c" in miss.thesis and miss.bias == pytest.approx(base.bias)


def test_all_without_data_is_none():
    assert synthesize([rep("a", 0, 0, "no_data")]) is None and synthesize([]) is None


def test_excluded_agents_do_not_vote():
    s = synthesize([rep("a", 0.5), rep("plan", -1.0, 1.0)])
    assert s.bias == pytest.approx(0.5) and "plan" not in s.contributions


def test_changing_weight_changes_result():
    rs = [rep("a", 0.8), rep("b", -0.4)]
    eq = synthesize(rs).bias
    heavy_a = synthesize(rs, SynthesisParams(weights={"a": 3.0})).bias
    heavy_b = synthesize(rs, SynthesisParams(weights={"b": 3.0})).bias
    assert heavy_b < eq < heavy_a


def test_regime_conditions_weights():
    p = SynthesisParams(regime_weights={"rango": {"a": 0.1}})
    rs = [rep("a", 0.8), rep("b", -0.4)]
    assert synthesize(rs, p, regime="rango").bias < synthesize(rs, p).bias
    assert "Régimen: rango" in synthesize(rs, p, regime="rango").thesis


def test_drift():
    s = synthesize([rep("a", 0.8), rep("b", 0.8)])
    assert drift_of(s, 0.01) == pytest.approx(0.8 * 0.8 * 0.1 * 0.01)
    assert drift_of(None, 0.01) is None
