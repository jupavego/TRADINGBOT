"""T60: el escuadrón de bots en la síntesis — papel por clase, peso medido, canales y cuarentena."""
from __future__ import annotations

import pytest

from eim.agents.bots import BotsAgent
from eim.agents.bots.params import params_of
from eim.bots.card import default_cards
from eim.bots.quarantine import Quarantine
from eim.core import AgentReport
from eim.synthesis import SynthesisParams, synthesize
from eim.synthesis.params import role_of
from eim.synthesis.squad import (
    apply,
    current_policy,
    default_params,
    policy_from_scorecard,
    set_policy,
    support,
)
from tests.bots.helpers import snapshot
from tests.bots.score_helpers import signal

BOT, STRAT = "hummingbot-directional", "s1"
KEY = f"{BOT}@{STRAT}"
CARDS = default_cards()


def rep(i: str, bias: float, conf: float = 0.8, **metrics) -> AgentReport:
    return AgentReport(agent_id=i, version="1", asof=0, bias=bias, confidence=conf,
                       horizon_bars=10, metrics=metrics)


def core() -> list[AgentReport]:
    return [rep("ema", 0.5), rep("structure", 0.4)]


def card_row(state="vota", weight=0.25, rho=0.2, mod=False) -> dict:
    return {"id": f"{BOT}:{STRAT}@1h@v1", "bot": BOT, "strategy": STRAT, "state": state,
            "initial_weight": weight if state == "vota" else 0.0, "publicable": False,
            "modulates_confidence": mod, "marginal": {"rho_max": rho}}


def sc(*rows, symbol="BTCUSDT") -> dict:
    return {"symbol": symbol, "bots": list(rows)}


def squad_report(stance: float, voters: int, mod=None, conf=0.8) -> AgentReport:
    return rep("bots", stance, conf if voters else 0.0, voters=voters, mod_disagreement=mod)


@pytest.fixture(autouse=True)
def _no_global_policy():
    set_policy(None)
    yield
    set_policy(None)


def policy(state="vota", cls="D", quarantined=(), symbol="BTCUSDT", **kw):
    cards = {BOT: CARDS[BOT].model_copy(update={"bot_class": cls})}
    return policy_from_scorecard(sc(card_row(state, **kw), symbol=symbol), cards, quarantined)


# --- sin votantes, la síntesis es idéntica a la previa -----------------------------------------
def test_all_informa_and_channels_off_is_identical_to_before():
    before = synthesize(core(), SynthesisParams())
    p = apply(SynthesisParams(), policy("informa"))
    assert p == SynthesisParams()                       # nada cambia: ni pesos ni excluidos
    after = synthesize([*core(), squad_report(0.9, 0)], p)
    assert after.bias == before.bias and after.agreement == before.agreement
    assert after.confidence == before.confidence and after.factors == before.factors


@pytest.mark.parametrize("state", ["informa", "rechazado", "deshabilitado_seguridad"])
def test_non_voting_state_never_moves_bias(state):
    ref = synthesize(core(), SynthesisParams())
    pol = policy(state, weight=0.25)
    agent = BotsAgent(provider=lambda: params_of(pol)).run(
        snapshot(bot_signals=[signal(1, -1.0, bot=BOT, strategy=STRAT)]))
    s = synthesize([*core(), agent], apply(SynthesisParams(), pol))
    assert s.bias == ref.bias and "bots" not in s.contributions


def test_quarantined_voter_does_not_vote():
    pol = policy("vota", quarantined={KEY})
    assert pol.get(KEY).state == "cuarentena" and not pol.voters
    assert apply(SynthesisParams(), pol) == SynthesisParams()


@pytest.mark.parametrize("cls", ["L", "IA"])
def test_lane_and_informing_classes_never_vote(cls):
    pol = policy("vota", cls=cls)
    assert not pol.voters and apply(SynthesisParams(), pol) == SynthesisParams()


# --- el bot que sí vota ---------------------------------------------------------------------------
def test_measured_weight_is_the_one_in_the_synthesis():
    pol = policy("vota", weight=0.25, rho=0.0)
    p = apply(SynthesisParams(), pol)
    assert p.weights["bots"] == 0.25 and "bots" not in p.excluded
    s = synthesize([*core(), squad_report(-1.0, 1)], p)
    assert s.weights["bots"] == 0.25 and s.contributions["bots"] < 0


def test_more_measured_weight_pulls_the_bias_more():
    bias = [synthesize([*core(), squad_report(-1.0, 1)],
                       apply(SynthesisParams(), policy("vota", weight=w, rho=0.0))).bias
            for w in (0.1, 0.25, 0.5)]
    assert bias[0] > bias[1] > bias[2]


def test_correlation_penalty_only_when_core_votes():
    p = apply(SynthesisParams(), policy("vota", weight=0.5, rho=0.6))
    with_core = synthesize([*core(), squad_report(-1.0, 1)], p)
    assert with_core.weights["bots"] == pytest.approx(0.5 * (1 - 0.6))
    alone = synthesize([squad_report(-1.0, 1)], p)
    assert alone.weights["bots"] == pytest.approx(0.5)


def test_squad_without_voters_is_skipped_not_diluting_confidence():
    p = apply(SynthesisParams(), policy("vota", weight=0.5, rho=0.0))
    ref = synthesize(core(), SynthesisParams(), expected=["ema", "structure"])
    s = synthesize([*core(), squad_report(0.0, 0)], p, expected=["ema", "structure", "bots"])
    assert s.confidence == pytest.approx(ref.confidence) and "bots" not in s.weights


def test_agent_votes_with_measured_weight_and_only_on_scored_symbol():
    sig = signal(1, 1.0, bot=BOT, strategy=STRAT)
    scored_elsewhere = BotsAgent(provider=lambda: params_of(policy("vota")))   # medido en BTC
    eth = scored_elsewhere.run(snapshot(bot_signals=[sig]))                    # fixture: ETHUSDT
    assert eth.metrics["voters"] == 0 and eth.bias == 0
    here = BotsAgent(provider=lambda: params_of(policy("vota", symbol="ETHUSDT")))
    out = here.run(snapshot(bot_signals=[sig]))
    assert out.metrics["voters"] == 1 and out.bias == 1.0
    assert out.metrics["bots"][0]["weight"] == 0.25


# --- canales que no votan -----------------------------------------------------------------------
def test_confidence_channel_off_by_default_even_with_split():
    s = synthesize([*core(), squad_report(0.0, 0, mod=1.0)], SynthesisParams())
    assert "escuadron" not in s.factors


def test_confidence_channel_lowers_confidence_on_extreme_split_only():
    p = SynthesisParams(squad_confidence=True)
    ref = synthesize(core(), p)
    split = synthesize([*core(), squad_report(0.0, 0, mod=1.0)], p)
    calm = synthesize([*core(), squad_report(0.0, 0, mod=0.3)], p)
    assert split.factors["escuadron"] == p.squad_conf
    assert split.confidence == pytest.approx(ref.confidence * p.squad_conf)
    assert "escuadron" not in calm.factors and split.bias == ref.bias


def test_policy_turns_the_channel_on_only_for_measured_moderators():
    assert apply(SynthesisParams(), policy("informa", mod=True)).squad_confidence is True
    assert apply(SynthesisParams(), policy("informa", mod=False)).squad_confidence is False
    assert apply(SynthesisParams(), policy("rechazado", mod=True)).squad_confidence is False


def test_second_opinion_counts_do_not_touch_probabilities():
    rows = [{"stance": 1.0, "status": "ok"}, {"stance": 1.0, "status": "ok"},
            {"stance": -1.0, "status": "ok"}, {"stance": 1.0, "status": "degraded"}]
    assert support(rows) == {"up": 2, "down": 1, "flat": 0, "total": 3}
    assert support([]) == {"up": 0, "down": 0, "flat": 0, "total": 0}


# --- papel, parámetros vigentes y cuarentena ----------------------------------------------------
def test_role_follows_the_policy():
    assert role_of("bots") == "contexto"
    set_policy(policy("vota"))
    assert role_of("bots", default_params()) == "direccional"
    assert default_params().weights["bots"] == 0.25


def test_set_policy_roundtrip():
    assert current_policy() is None
    pol = policy("informa")
    set_policy(pol)
    assert current_policy() is pol and default_params() == SynthesisParams()


def test_quarantine_persists_and_only_releases_by_hand(tmp_path):
    q = Quarantine(tmp_path)
    seen = []
    q.on_change.append(lambda: seen.append(1))
    assert q.trip(KEY, "falla del ejecutor", 10) and not q.trip(KEY, "otra vez", 11)
    assert Quarantine(tmp_path).keys() == frozenset({KEY})         # sobrevive al reinicio
    assert q.release(KEY, 20) and not q.release(KEY, 21) and len(seen) == 2
    log = (tmp_path / "quarantine.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(log) == 2 and '"trip"' in log[0] and '"release"' in log[1]
