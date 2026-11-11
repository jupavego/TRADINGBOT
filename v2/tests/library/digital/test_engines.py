"""T153–T157: consenso ponderado, contraste dirigido, diagnóstico, perfiles y aprendizaje."""

from __future__ import annotations

import random

from eim.library.digital.catalog import overview, related_strategies, search
from eim.library.digital.consensus import KnowledgeBase, consensus, contradictions
from eim.library.digital.contrast import CachedContrast, TradeContext, contrast
from eim.library.digital.diagnose import diagnose, numbers
from eim.library.digital.learning import MIN_N, evaluate
from eim.library.digital.profiles import LENSES
from eim.library.schema import KnowledgeCard
from tests.library.digital.conftest import make_ref, st


def test_consensus_weighs_quality_not_count(kb):
    assert consensus(kb, "momentum")["verdict"] == "a favor"
    assert consensus(kb, "breakout")["verdict"] == "dividido"
    assert consensus(kb, "nonexistent")["verdict"] == "sin evidencia"
    assert consensus(kb, "mean_reversion")["verdict"] == "condicionado"
    # una teoría pesa menos que una evidencia empírica en cripto
    strong = make_ref("e", "F", [st("momentum", "objeta")], markets=("cripto",), year=2021)
    weak = [make_ref(f"h{i}", "E", [st("momentum", "apoya", "hipotesis")], reliability="baja")
            for i in range(3)]
    d = consensus(KnowledgeBase.build([strong, *weak]), "momentum")
    assert d["objection_mass"] > d["support_mass"] and d["verdict"] == "en contra"
    assert any(c["concept"] == "breakout" for c in contradictions(kb))


def test_local_cards_join_the_base():
    card = KnowledgeCard(
        id="nison_x", title="Momentum de velas", kind="regla", claim="Las velas momentum.",
        author_evidence="a", applicability={"original_market": ["acciones"], "timeframe": "1h",
                                            "crypto_24_7": "s"}, testable=False,
        verification="pendiente")
    kb = KnowledgeBase.build([], local=[card])
    ev = [e for es in kb.by_concept.values() for e in es]
    assert ev and all(e.local and e.level == "hipotesis" for e in ev)


def test_contrast_is_selective_and_directional(kb):
    with_trend = contrast(kb, TradeContext(side=1, strategy="ind_supertrend@1h", trend=1))
    assert "trend_following" in with_trend["backs"]
    assert with_trend["sources_consulted"] < len(kb.refs) + 1
    against = contrast(kb, TradeContext(side=-1, strategy="ind_supertrend@1h", trend=1))
    assert "trend_following" in against["contradicts"]
    assert against["concepts"]["trend_following"]["direction_note"]
    by_regime = contrast(kb, TradeContext(side=-1, strategy="agente_ema", regime="trend_up"))
    assert "trend_following" in by_regime["contradicts"]
    ranging = contrast(kb, TradeContext(side=1, strategy="ind_supertrend", regime="range"))
    assert ranging["concepts"]["trend_following"]["verdict"] == "condicionado"
    fc = contrast(kb, TradeContext(side=1, strategy="consenso_fuerte"))
    assert "forecast_eval" not in fc["entry_concepts"] and "forecast_eval" in fc["context_concepts"]
    cc = CachedContrast(kb)
    ctx = TradeContext(side=1, strategy="ind_donchian@1h")
    assert cc(ctx) is cc(ctx)


def test_diagnose_numbers_and_profiles(kb):
    n = numbers({"fill": 100.0, "sl": 98.0, "tp": 104.0, "leverage": 10, "qty": 1.0,
                 "fees": 0.2, "slip": 0.1})
    assert abs(n["rr"] - 2.0) < 1e-9 and abs(n["breakeven_winrate"] - 1 / 3) < 1e-9
    assert abs(n["liq_pct"] - 9.6) < 1e-9 and n["liq_ratio"] > 1 and abs(n["cost_r"] - 0.15) < 1e-9
    risky = diagnose(kb, {"side": 1, "fill": 100, "sl": 85, "leverage": 10, "strategy":
                          "ind_donchian", "profile": "agresivo"})
    liq = next(d for d in risky["dimensions"] if d["id"] == "liquidation")
    assert liq["assessment"] == "crítico" and liq["refs"]
    assert len(risky["dimensions"]) == 10 and "no ejecuta" in risky["conclusion"]
    cons = diagnose(kb, {"side": 1, "fill": 100, "sl": 99, "strategy": "ind_donchian",
                         "profile": "conservador"}, stats={"n": 5})
    assert any("consenso a favor" in x for x in cons["profile_notes"])
    prob = next(d for d in cons["dimensions"] if d["id"] == "probability")
    assert prob["assessment"] == "insuficiente"
    assert set(LENSES) == {"conservador", "moderado", "agresivo", "ppp_btcusdt"}


def test_learning_needs_samples(kb):
    few = [{"ledger_id": f"a{i}", "side": 1, "strategy": "ind_supertrend", "r": 0.5}
           for i in range(5)]
    res = evaluate(few, kb)
    assert res["n_traces"] == 5 and "insuficiente" in res["verdict"]
    t = res["traces"][0]
    assert set(t) >= {"operacion", "diagnostico", "estrategia", "literatura", "resultado",
                      "conclusion"}
    rnd = random.Random(1)
    rows = [{"ledger_id": f"b{i}", "side": 1, "strategy": "ind_supertrend",
             "r": rnd.gauss(0.6, 0.5)} for i in range(MIN_N + 5)]
    rows += [{"ledger_id": f"c{i}", "side": 1, "strategy": "ind_rsi", "r": rnd.gauss(-0.6, 0.5)}
             for i in range(MIN_N + 5)]
    ta = make_ref("rsi_no", "A", [st("mean_reversion", "objeta")], markets=("cripto",))
    sr = make_ref("sr_no", "A", [st("support_resistance", "objeta")], markets=("cripto",))
    kb2 = KnowledgeBase.build([*kb.refs.values(), ta, sr])
    res = evaluate(rows, kb2)
    assert res["backed"]["n"] >= MIN_N and res["contradicted"]["n"] >= MIN_N
    assert "mejor" in res["verdict"]
    useful = {c["concept"]: c["useful"] for c in res["concepts"]}
    assert "anticipa" in useful["trend_following"]          # juzgado por R medio, no por acierto


def test_catalog_search_and_overview(kb):
    refs = list(kb.refs.values())
    assert [r.id for r in search(refs, category="F")] == ["liq_a"]
    assert search(refs, author="pérez")
    assert "ind_donchian" in related_strategies(kb.refs["brk_a"])
    o = overview(refs, {}, local_books=7, local_cards=138)
    assert o["digital_total"] == len(refs) and o["total_references"] == len(refs) + 7
