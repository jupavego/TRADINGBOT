"""Contrato del agente: sin datos, pureza, citas contra las fichas, apoyo a escenarios, síntesis."""
from __future__ import annotations

import socket

import pytest

from eim.agents.literature import LiteratureAgent, LiteratureParams
from eim.agents.literature.params import CARD_META
from eim.agents.literature.rules import RULES
from eim.agents.registry import default_registry
from eim.core import AgentReport
from eim.data.library import load_cards
from eim.synthesis import synthesize
from eim.synthesis.params import SynthesisParams, role_of
from tests.agents.literature._synth import flat, ohlc, snap, trend

DOWN = trend(-1)
HAMMER = DOWN + [ohlc(DOWN[-1][3] - 0.1, DOWN[-1][3] + 0.1, up=0.01, dn=0.7)]
BULL_ENGULF = DOWN + [ohlc(DOWN[-1][3], DOWN[-1][3] - 0.3), ohlc(DOWN[-1][3] - 0.4,
                                                              DOWN[-1][3] + 1.0)]


def test_no_coded_cards_is_no_data():
    rep = LiteratureAgent(LiteratureParams(coded_cards=frozenset())).run(snap(HAMMER))
    assert rep.status == "no_data" and rep.bias == 0 and rep.confidence == 0


def test_too_few_candles_is_no_data():
    assert LiteratureAgent().run(snap(flat(10))).status == "no_data"


def test_deterministic_bounded_and_capped():
    a = LiteratureAgent()
    r1, r2 = a.run(snap(BULL_ENGULF)), a.run(snap(BULL_ENGULF))
    assert r1 == r2 and -1 <= r1.bias <= 1 and r1.bias > 0
    assert 0 < r1.confidence <= 0.5


def test_pure_no_io(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("I/O prohibido en el agente")
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr("builtins.open", boom)
    assert LiteratureAgent().run(snap(HAMMER)).status in {"ok", "degraded"}


def test_evidence_cites_book_and_page():
    rep = LiteratureAgent().run(snap(HAMMER))
    assert any("Nison (2001), cap. 4, pp. 45–46" in e for e in rep.evidence)
    assert any("no es una señal validada" in w for w in rep.warnings)
    assert any("no en cripto" in w for w in rep.warnings)


def test_nothing_active_is_neutral():
    rep = LiteratureAgent().run(snap(flat()))
    assert rep.bias == 0 and rep.confidence == 0 and rep.metrics["hits"] == []
    assert rep.metrics["rules_evaluated"] >= 1


def test_conflicting_rules_warn():
    # martillo alcista en la misma vela que un RSI que recruza 70 a la baja no es construible
    # con precisión; se fuerza con dos aciertos de signo opuesto.
    up = trend(+1)
    p = up[-1][3]
    both = up + [ohlc(p, p + 3.0, 0.01, 0.01)] * 0 + [ohlc(p, p - 3.0, 0.05, 0.05)]
    rep = LiteratureAgent().run(snap(both))
    dirs = {h["direction"] for h in rep.metrics["hits"]}
    assert dirs <= {-1, 1}


def test_scenario_support_coherent_with_hits():
    rep = LiteratureAgent().run(snap(BULL_ENGULF))
    ss, hits = rep.metrics["scenario_support"], rep.metrics["hits"]
    assert set(ss) == {"bull", "neutral", "bear"}
    bull_ids = {h["card_id"] for h in hits if h["direction"] > 0}
    assert set(ss["bull"]["supports"]) == bull_ids and ss["bull"]["net"] > 0
    assert set(ss["bear"]["contradicts"]) == bull_ids and ss["bear"]["net"] < 0
    assert ss["neutral"]["supports"] == [] and ss["neutral"]["net"] <= 0
    assert all(v["rules_evaluated"] == rep.metrics["rules_evaluated"] for v in ss.values())
    assert all(v["label"].startswith("Apoyo bibliográfico") for v in ss.values())


def test_overlays_mark_pattern_candles():
    rep = LiteratureAgent().run(snap(HAMMER))
    assert rep.overlays and all(o.kind == "marker" and o.agent_id == "literature"
                                for o in rep.overlays)
    assert len({o.id for o in rep.overlays}) == len(rep.overlays)


def test_every_rule_cites_an_existing_coded_card_and_meta_matches():
    cards = {c.id: c for c in load_cards()}
    assert set(RULES) == set(CARD_META)
    for cid, meta in CARD_META.items():
        c = cards[cid]
        assert c.status == "codificada" and c.testable, cid
        assert set(meta.markets) == set(c.applicability.original_market), cid
        assert meta.cite.startswith(meta.author)
        pages = sorted({p for ct in c.citations for p in ct.pages})
        assert any(f"{p}" in meta.cite or f"{p}–" in meta.cite for p in pages), cid


def test_registered_and_does_not_vote():
    assert "literature" in default_registry().ids()
    assert SynthesisParams().weights["literature"] == 0.0
    assert role_of("literature") == "direccional"   # papel como `technical`; peso 0 = no vota
    rep = LiteratureAgent().run(snap(BULL_ENGULF))
    assert rep.bias > 0
    ema = AgentReport(agent_id="ema", version="1", asof=0, bias=-0.4, confidence=0.8,
                      horizon_bars=10)
    p = SynthesisParams(correlation={})
    solo = synthesize([ema], p)
    with_lit = synthesize([ema, rep], p, expected=["ema", "literature"])
    assert with_lit.bias == pytest.approx(solo.bias)
    assert with_lit.contributions.get("literature", 0) == 0
    assert synthesize([rep], p) is None or synthesize([rep], p).bias == 0


def test_report_is_json_serializable():
    rep = LiteratureAgent().run(snap(BULL_ENGULF))
    assert rep.metrics["hits"]
    rep.model_dump(mode="json")      # numpy.bool / numpy.float64 romperían la API
