"""Agente `arbitrage` (T39) sobre las fotografías sintéticas de T38 y el fixture real."""

from __future__ import annotations

from pathlib import Path

import pytest

from eim.agents.arbitrage import LABEL, ArbAgentParams, ArbitrageAgent
from eim.agents.registry import default_registry
from eim.arbitrage import ArbParams, scan_all
from eim.core import ArbMarket, CostModel, SpotPair
from eim.data.arb_store import arb_snapshot
from eim.synthesis import synthesize
from eim.synthesis.params import SynthesisParams
from tests.arbitrage.helpers import (
    ASOF,
    book,
    carry_market,
    history,
    market,
    perp,
    premium,
    quarterly,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "arbitrage" / "binance_arb_2026-10-15.json"
P = ArbAgentParams(engine=ArbParams(assets=("BTC",)))


def full_market(*, levels: int = 20, qty: float = 5.0) -> ArbMarket:
    """BTC con las cuatro estrategias: spot, perpetuos USDT/USDC, trimestral y ciclo ETH."""
    kw = {"levels": levels, "qty": qty}
    spot = {"BTCUSDT": book(60_000, **kw), "ETHUSDT": book(2_400, **kw),
            "ETHBTC": book(0.04, **kw), "USDCUSDT": book(0.9998, step_bps=0.1, **kw)}
    pairs = [SpotPair(symbol="BTCUSDT", base="BTC", quote="USDT"),
             SpotPair(symbol="ETHUSDT", base="ETH", quote="USDT"),
             SpotPair(symbol="ETHBTC", base="ETH", quote="BTC"),
             SpotPair(symbol="USDCUSDT", base="USDC", quote="USDT")]
    q = quarterly("BTC", 60)
    return market(
        spot=spot, pairs=pairs,
        futures={"BTCUSDT": book(60_010, **kw), "BTCUSDC": book(60_030, **kw),
                 q.symbol: book(60_900, **kw)},
        prem={"BTCUSDT": premium("BTCUSDT", 0.0004, mark=60_010, index=60_000),
              "BTCUSDC": premium("BTCUSDC", 0.0003, mark=60_030, index=60_000)},
        hist={"BTCUSDT": history(0.0003), "BTCUSDC": history(0.0002)},
        contracts=[perp("BTC"), perp("BTC", "USDC"), q])


def run(mkt: ArbMarket | None, age_s: float = 0.0, p: ArbAgentParams = P):
    return ArbitrageAgent(p).analyze(arb_snapshot(mkt, (mkt.asof if mkt else ASOF)
                                                  + int(age_s * 1000)))


def test_normal_case_neutral_with_breakdown_from_t38():
    mkt = full_market()
    res, rep = run(mkt)
    assert rep.status == "ok" and rep.bias == 0 and 0 < rep.confidence <= 1
    m = rep.metrics
    assert m["mode"] == "ANALISIS" and m["label"] == LABEL == "neto estimado, no garantizado"
    assert m["neutral"] is True and rep.overlays == []
    assert [s["status"] for s in m["scans"]] == ["ok"] * 4
    # el desglose es el del motor T38, no un recálculo
    ref = scan_all(mkt, CostModel(), P.engine).selection
    assert m["counts"] == {"valued": len(ref.selected) + len(ref.rejected),
                           "selected": len(ref.selected), "rejected": len(ref.rejected)}
    assert m["best"], "con base trimestral amplia debe haber al menos una seleccionada"
    for row, r in zip(m["best"], ref.selected, strict=False):
        o = r.opportunity
        assert row["net"] == pytest.approx(o.net_edge, abs=0.01)
        assert row["gross"] == pytest.approx(o.gross_edge, abs=0.01)
        assert row["costs"]["fees"] == pytest.approx(o.costs.fees, abs=0.01)
        assert row["costs"]["slippage"] == pytest.approx(o.costs.slippage, abs=0.01)
        assert row["costs"]["funding"] == pytest.approx(o.costs.funding, abs=0.01)
        assert row["net"] == pytest.approx(row["gross"] - row["costs"]["total"], abs=0.02)
        assert row["selected"] and row["reason"] is None and row["legs"]
    assert res is not None and len(res.scans) == 4
    assert any("Neutral al mercado" in e for e in rep.evidence)


def test_bias_always_zero_even_with_huge_edge():
    _, rep = run(carry_market(0.01, realized=0.01))  # funding 1 %/8 h: carry enorme
    assert rep.metrics["best"] and rep.metrics["best"][0]["net"] > 0
    assert rep.bias == 0


def test_no_data_without_snapshot_photo():
    res, rep = run(None)
    assert res is None
    assert rep.status == "no_data" and rep.bias == 0 and rep.confidence == 0
    assert "escáner" in rep.warnings[0]


def test_no_data_when_no_strategy_can_value():
    _, rep = run(market(errors={"contracts": "HTTP 503", "spot_pairs": "HTTP 503"}))
    assert rep.status == "no_data" and rep.confidence == 0
    assert any("falta" in w for w in rep.warnings)


def test_deterministic():
    mkt = full_market()
    assert run(mkt)[1].model_dump() == run(mkt)[1].model_dump()


def test_confidence_decays_with_age_and_staleness_degrades():
    mkt = full_market()
    fresh, mid_age, stale = run(mkt, 5)[1], run(mkt, 60)[1], run(mkt, 400)[1]
    assert fresh.confidence > mid_age.confidence > stale.confidence == 0
    assert fresh.metrics["quality"]["freshness"] == 1
    assert stale.status == "degraded"
    assert "fotografía de hace" in mid_age.warnings[0]
    assert all(r.bias == 0 for r in (fresh, mid_age, stale))


def test_confidence_drops_with_thin_books():
    deep = run(full_market())[1]
    shallow = run(full_market(levels=5))[1]  # 5 niveles < 20 por lado
    thin = run(full_market(qty=0.005))[1]  # 20 × 0,005 BTC < 0,167 BTC del nocional
    assert shallow.metrics["quality"]["book_score"] == pytest.approx(0.25)
    assert shallow.confidence < deep.confidence
    assert thin.metrics["quality"]["executable_frac"] < 1
    assert thin.confidence < deep.confidence
    assert thin.metrics["rejected_by_code"].get("incomplete", 0) > 0


def test_rejected_have_reasons_and_counts():
    m = run(full_market())[1].metrics
    assert sum(m["rejected_by_code"].values()) == len(m["rejected"]) == m["counts"]["rejected"]
    assert all(r["reason"] and r["code"] for r in m["rejected"])
    assert m["rejected_by_code"].get("informative", 0) >= 1  # triangular: informativo (T33)


def test_funding_and_basis_tables():
    m = run(full_market())[1].metrics
    f = m["funding"]["BTCUSDT"]
    assert f["predicted"] == 0.0004 and f["interval_h"] == 8
    assert f["predicted_annual"] == pytest.approx(0.0004 * 3 * 365)
    assert f["realized_mean"] == pytest.approx(0.0003) and f["realized_n"] == 21
    assert len(f["history"]) == 21 and f["next_funding_t"] > ASOF
    assert set(m["funding"]) == {"BTCUSDT", "BTCUSDC"}
    q = next(b for b in m["basis"] if b["kind"] == "quarterly")
    s_mid = 60_000.0
    b = (60_900 - s_mid) / s_mid
    assert q["basis_bps"] == pytest.approx(b * 1e4, abs=1e-3)
    assert q["annualized"] == pytest.approx(b * 365 / 60, rel=1e-4)
    pr = next(b for b in m["basis"] if b["kind"] == "perpetual")
    assert pr["annualized"] is None


def test_real_fixture_breakdown_matches_engine():
    mkt = ArbMarket.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    res, rep = ArbitrageAgent().analyze(arb_snapshot(mkt, mkt.asof + 2000))
    ref = scan_all(mkt)
    assert rep.bias == 0 and rep.status == "ok"
    assert [r.opportunity.net_edge for r in res.selection.selected] == [
        r.opportunity.net_edge for r in ref.selection.selected]
    assert rep.metrics["counts"]["valued"] == 28
    assert set(rep.metrics["funding"]) == {"BTCUSDT", "ETHUSDT", "BTCUSDC", "ETHUSDC"}


def test_registered_and_excluded_from_directional_synthesis():
    reg = default_registry()
    assert reg.get("arbitrage").version == ArbitrageAgent.version
    assert "arbitrage" in SynthesisParams().excluded
    rep = run(full_market())[1]
    assert synthesize([rep]) is None  # solo, no aporta nada a la tesis direccional
