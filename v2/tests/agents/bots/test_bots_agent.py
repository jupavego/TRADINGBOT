"""Agente `bots` (T57): consolida posturas ya calculadas; sin estado `vota` no mueve el sesgo."""

import pytest

from eim.agents.bots import BotsAgent, BotsParams
from eim.agents.runner import run_agents
from eim.bots.adapter import empty_signal
from eim.bots.card import card_of
from eim.bots.hb_directional import HummingbotDirectionalAdapter
from eim.core import NOT_SAVED, VERSION_CHANGED, AgentReport, BotQuality, BotSignal
from eim.synthesis import synthesize
from eim.synthesis.params import SynthesisParams, role_of
from tests.bots.helpers import snapshot

SHA = "9af100d6822da7d2d0291a906c730ef172284ee2"


def sig(strategy="a", stance=1.0, confidence=None, status="ok", notes=(), bot_id="b",
        horizon=None, version=None) -> BotSignal:
    return BotSignal(
        bot_id=bot_id, strategy=strategy, version=version or f"{SHA}+0123456789ab", asof=2000,
        timeframe="1h", symbol="ETHUSDT", stance=stance, confidence=confidence,
        horizon_bars=horizon, evidence=[f"{strategy} {stance}"],
        data_quality=BotQuality(bars=5, last_candle_t=1000, notes=list(notes)), status=status)


def snap(*sigs, n=300):
    return snapshot(n).model_copy(update={"bot_signals": list(sigs) or None})


def test_without_signals_is_no_data_with_zero_bias():
    r = BotsAgent().run(snap())
    assert r.status == "no_data" and r.bias == 0 and r.confidence == 0 and r.warnings


def test_all_no_data_signals_is_no_data():
    s = sig(stance=0.0, status="no_data")
    assert BotsAgent().run(snap(s)).status == "no_data"


def test_a_bot_that_is_not_in_state_vota_does_not_move_the_bias():
    r = BotsAgent().run(snap(sig("a", 1.0, 0.9), sig("b", 1.0, 0.8)))
    assert r.bias == 0 and r.confidence == 0 and r.status == "ok"
    assert r.metrics["voters"] == 0 and r.metrics["signals"] == 2
    assert all(b["votes"] is False and b["state"] == "observa" for b in r.metrics["bots"])
    assert any("«vota»" in e for e in r.evidence)
    # estados que no son «vota» tampoco votan
    p = BotsParams(states={"b@a": "degradado", "b@b": "observa"})
    assert BotsAgent(p).run(snap(sig("a", 1.0, 0.9), sig("b", -1.0, 0.8))).bias == 0


def test_bias_is_the_confidence_weighted_mean_of_voters_only():
    p = BotsParams(states={"b@a": "vota", "b@b": "vota"})   # c queda «observa»
    r = BotsAgent(p).run(snap(sig("a", 1.0, 0.9), sig("b", -1.0, 0.3), sig("c", -1.0, 1.0)))
    assert r.bias == pytest.approx((0.9 - 0.3) / 1.2) and r.metrics["voters"] == 2
    assert r.confidence == pytest.approx(0.6) and -1 <= r.bias <= 1
    assert {b["strategy"] for b in r.metrics["bots"] if b["votes"]} == {"a", "b"}


def test_voter_without_confidence_gets_neutral_weight_and_a_declared_assumption():
    p = BotsParams(states={"b@a": "vota"})
    r = BotsAgent(p).run(snap(sig("a", 1.0, None)))
    assert r.bias == 1.0 and r.confidence == p.fallback_confidence
    assert any("sin confianza propia" in w for w in r.warnings)


def test_degraded_bot_warns_and_does_not_vote():
    p = BotsParams(states={"b@a": "vota", "b@b": "vota"})
    bad = sig("a", 0.0, status="degraded")
    r = BotsAgent(p).run(snap(bad, sig("b", -1.0, 0.5)))
    assert r.status == "degraded" and any("b@a: degradado" in w for w in r.warnings)
    assert r.bias == -1.0 and r.metrics["voters"] == 1


def test_version_change_is_warned():
    note = f"{VERSION_CHANGED}: 9af100d6822d+aaaaaaaaaaaa → 9af100d6822d+bbbbbbbbbbbb"
    s = sig("a", notes=[note])
    r = BotsAgent().run(snap(s))
    assert any("a" in w and VERSION_CHANGED in w for w in r.warnings)
    assert r.metrics["bots"][0]["version"] == s.version


def test_unsaved_signal_is_warned():
    r = BotsAgent().run(snap(sig("a", notes=[f"{NOT_SAVED}: RuntimeError: disco"])))
    assert any(NOT_SAVED in w for w in r.warnings)


def test_metrics_carry_each_bot_stance_confidence_version_and_state():
    r = BotsAgent().run(snap(sig("a", 1.0, 0.7), sig("b", -1.0, None)))
    row = r.metrics["bots"][0]
    assert {"bot_id", "strategy", "stance", "confidence", "version", "status", "state"} <= set(row)
    assert row["stance"] == 1.0 and row["confidence"] == 0.7 and row["state"] == "observa"


def test_disagreement_is_the_dispersion_of_stances():
    same = BotsAgent().run(snap(sig("a", 1.0), sig("b", 1.0)))
    opposed = BotsAgent().run(snap(sig("a", 1.0), sig("b", -1.0)))
    assert same.metrics["disagreement"] == 0 and opposed.metrics["disagreement"] == pytest.approx(1)
    assert BotsAgent().run(snap(sig("a", 1.0))).metrics["disagreement"] is None


def test_horizon_is_the_median_of_the_voters():
    p = BotsParams(states={"b@a": "vota", "b@b": "vota", "b@c": "vota"})
    r = BotsAgent(p).run(snap(sig("a", 1.0, 0.5, horizon=4), sig("b", 1.0, 0.5, horizon=8),
                              sig("c", 1.0, 0.5, horizon=12)))
    assert r.horizon_bars == 8


def test_deterministic_and_valid_report():
    s = snap(sig("a", 1.0, 0.5), sig("b", -1.0, 0.4))
    a, b = BotsAgent().run(s), BotsAgent().run(s)
    assert a == b and isinstance(a, AgentReport) and a.agent_id == "bots"
    assert "bot_signals" in BotsAgent.requires


def test_with_the_real_adapter_signals():
    snapshot_ = HummingbotDirectionalAdapter().signals(snapshot(300))
    r = BotsAgent().run(snapshot(300).model_copy(update={"bot_signals": snapshot_}))
    assert r.status == "ok" and r.bias == 0 and r.metrics["signals"] == 2
    assert {b["bot_id"] for b in r.metrics["bots"]} == {"hummingbot-directional"}
    assert all(b["source"] == "fixture" and b["coverage"] == 1.0 for b in r.metrics["bots"])


def test_runner_integration_and_exception_safety():
    (rep,) = run_agents([BotsAgent()], snap(sig("a", 1.0, 0.5)))
    assert rep.agent_id == "bots" and rep.status == "ok"
    (none,) = run_agents([BotsAgent()], snapshot(300))
    assert none.status == "no_data"


# --- no vota en la síntesis -------------------------------------------------------------------
def test_synthesis_ignores_bots_even_if_they_vote_in_the_agent():
    p = BotsParams(states={"b@a": "vota"})
    loud = BotsAgent(p).run(snap(sig("a", 1.0, 1.0)))
    assert loud.bias == 1.0 and loud.confidence == 1.0
    other = AgentReport(agent_id="structure", version="1", asof=2000, bias=-0.5, confidence=0.8,
                        horizon_bars=10)
    with_bots = synthesize([other, loud])
    without = synthesize([other])
    assert with_bots.bias == without.bias and "bots" not in with_bots.contributions
    assert with_bots.weights.get("bots", 0) == 0
    assert synthesize([loud]) is None                   # solo bots: nadie aporta


def test_role_is_context_while_excluded_and_directional_once_enabled():
    assert role_of("bots") == "contexto"
    enabled = SynthesisParams(excluded=frozenset({"plan", "calendar", "arbitrage", "regime"}))
    assert role_of("bots", enabled) == "direccional"
    assert SynthesisParams().weights["bots"] == 0.0


def test_empty_signal_card_is_the_audited_one():
    s = empty_signal(card_of("hummingbot-directional"), "x", f"{SHA}+0123456789ab", snapshot(),
                     "degraded", "m")
    assert BotsAgent().run(snap(s)).status == "degraded"
