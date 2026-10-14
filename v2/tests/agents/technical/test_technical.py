"""Agente `technical`: sesgos esperados, anti-redundancia, multi-marco, régimen y contrato."""
from __future__ import annotations

import numpy as np
import pytest

from eim.agents.registry import default_registry
from eim.agents.runner import run_agents
from eim.agents.technical import TechnicalAgent, TechnicalParams
from eim.agents.technical.frame import analyze, resample
from eim.agents.technical.params import FAMILIES
from eim.agents.technical.rules import NO_VOTE, RULES, Ctx, evaluate
from eim.core import MarketSnapshot
from eim.indicators import SPECS, candle_arrays
from tests.agents.conftest import make_snapshot
from tests.agents.technical._synth import HOUR, candles, snapshot

SEEDS = range(6)


@pytest.mark.parametrize("seed", SEEDS)
def test_trend_series_give_expected_sign(seed):
    up = TechnicalAgent().run(snapshot("up", seed=seed))
    down = TechnicalAgent().run(snapshot("down", seed=seed))
    assert up.bias > 0.25 and down.bias < -0.25
    assert up.metrics["regime"]["label"] == down.metrics["regime"]["label"] == "tendencia"
    assert up.status == "ok"


def test_range_series_is_near_neutral_and_less_confident():
    rng = [TechnicalAgent().run(snapshot("range", seed=s)) for s in SEEDS]
    trend = [TechnicalAgent().run(snapshot("up", seed=s)) for s in SEEDS]
    assert abs(np.mean([r.bias for r in rng])) < 0.15
    assert np.mean([abs(r.bias) for r in rng]) < np.mean([abs(r.bias) for r in trend]) / 2
    assert np.mean([r.confidence for r in rng]) < np.mean([r.confidence for r in trend])
    labels = [r.metrics["regime"]["label"] for r in rng]
    assert labels.count("tendencia") < len(labels) / 2


def test_few_candles_is_no_data():
    r = TechnicalAgent().run(snapshot("up", n=50))
    assert r.status == "no_data" and r.bias == 0 and r.confidence == 0 and r.warnings


def test_empty_snapshot_is_no_data():
    snap = MarketSnapshot(symbol="X", timeframe="1h", candles=[], asof=0)
    assert TechnicalAgent().run(snap).status == "no_data"


def test_duplicating_an_indicator_does_not_change_bias():
    snap = snapshot("up", seed=3)
    base = TechnicalAgent().run(snap)
    rules = dict(RULES)
    rules["RSI_copia"] = RULES["RSI"]
    rules["SAR_copia"] = RULES["SAR"]
    dup = TechnicalAgent(rules=rules).run(snap)
    assert dup.bias == pytest.approx(base.bias, abs=1e-12)
    assert dup.confidence == pytest.approx(base.confidence, abs=1e-12)
    assert dup.metrics["duplicates"] == {"RSI_copia": "RSI", "SAR_copia": "SAR"}


def test_correlated_indicators_share_one_group():
    r = TechnicalAgent().run(make_snapshot())
    groups = r.metrics["families"]["tendencia"]["clusters"]
    assert any({"MA", "EMA"} <= set(g) for g in groups)


def test_every_catalog_indicator_votes_or_says_why():
    assert set(RULES) | set(NO_VOTE) == set(SPECS)
    assert {r.family for r in RULES.values()} == set(FAMILIES)


def test_rules_have_no_look_ahead():
    data = candle_arrays(candles("up", 400, seed=1))
    full, _ = evaluate(Ctx(data=data, rp=TechnicalParams().rules), RULES)
    for cut in (250, 330):
        part, _ = evaluate(Ctx(data={k: v[:cut] for k, v in data.items()},
                               rp=TechnicalParams().rules), RULES)
        for k in RULES:
            np.testing.assert_allclose(part[k], full[k][:cut], equal_nan=True, err_msg=k)


def test_regime_reweights_families():
    p = TechnicalParams()
    fr = analyze(candles("up", seed=0), p, RULES)
    assert fr.regime[-1] == 0  # tendencia
    w = p.family_weights
    assert w["tendencia"]["tendencia"] > w["rango"]["tendencia"]
    assert w["rango"]["momentum"] > w["tendencia"]["momentum"]


def test_lower_frame_disagreement_lowers_confidence():
    snap = snapshot("up", seed=2)
    step15 = HOUR // 4

    def with_lower(kind: str) -> MarketSnapshot:
        return snap.model_copy(update={"candles_tf": {"15m": candles(kind, 600, seed=5,
                                                                      step=step15)}})

    agree = TechnicalAgent().run(with_lower("up"))
    clash = TechnicalAgent().run(with_lower("down"))
    assert agree.metrics["mtf_agreement"] == 1.0
    assert clash.metrics["mtf_agreement"] < 1.0
    assert clash.confidence < agree.confidence
    assert clash.bias == agree.bias  # el sesgo es el del marco del snapshot
    assert set(agree.metrics["frames"]) == {"1h", "15m", "4h"}
    assert "agregado" in agree.metrics["frames"]["4h"]["source"]


def test_resample_keeps_only_complete_groups():
    cs = candles("up", 10, step=HOUR)  # T0 alineado a 4h → 2 grupos completos + 2 velas sueltas
    out = resample(cs, 4 * HOUR)
    assert len(out) == 2
    assert out[0].o == cs[0].o and out[0].c == cs[3].c
    assert out[0].h == max(c.h for c in cs[:4]) and out[0].v == pytest.approx(
        sum(c.v for c in cs[:4]))


def test_fixture_report_contract():
    r = TechnicalAgent().run(make_snapshot())
    assert -1 <= r.bias <= 1 and 0 <= r.confidence <= TechnicalParams().max_confidence
    assert r.status == "degraded"  # la fixture no trae taker_buy_v → familia flujo sin datos
    assert any("flujo" in w for w in r.warnings)
    assert r.metrics["families"]["flujo"]["vote"] is None
    assert len(r.metrics["votes"]) == len(RULES)
    ev = [e for e in r.evidence if e.startswith("Tendencia")]
    assert ev and ev[0].count(";") <= 2  # máximo 3 reglas por familia
    assert {o.id for o in r.overlays} >= {"technical:boll:up", "technical:sar", "technical:super"}
    assert all(o.agent_id == "technical" and o.kind == "level" for o in r.overlays)


def test_deterministic():
    snap = snapshot("down", seed=4)
    assert TechnicalAgent().run(snap) == TechnicalAgent().run(snap)


def test_registered_and_runs_in_runner():
    reg = default_registry()
    agent = reg.get("technical")
    [rep] = run_agents([agent], snapshot("up", seed=0))
    assert rep.agent_id == "technical" and rep.status == "ok"
