"""Balance ganadas/perdidas: ponderado de los perfiles, periodos y retroalimentación."""

from __future__ import annotations

import pytest

from eim.paper.balance import DAY_MS, balance, summarize

NOW = 1_800_000_000_000


def tr(pnl: float, r: float, *, exit_days: float = 1, strategy: str = "a", side: int = 1,
       reason: str | None = None, cost: float = 1.0) -> dict:
    return {"pnl": pnl, "r": r, "exit_t": NOW - int(exit_days * DAY_MS), "strategy": strategy,
            "side": side, "reason": reason or ("TP" if pnl > 0 else "SL"), "fees": cost,
            "slip": 0.0, "funding": 0.0}


def test_summary_counts_and_ratios():
    ts = [tr(20, 2), tr(10, 1), tr(-10, -1), tr(-10, -1), tr(0, 0, reason="TIEMPO")]
    s = summarize(ts)
    assert (s["n"], s["wins"]["n"], s["losses"]["n"]) == (5, 2, 3)   # PnL 0 cuenta como perdida
    assert s["win_rate"] == pytest.approx(0.4)
    assert s["wins"]["usd"] == 30 and s["losses"]["usd"] == -20 and s["net"] == 10
    assert s["pf"] == pytest.approx(1.5)
    assert s["payoff"] == pytest.approx(1.5 / (2 / 3))               # R medio ganado / perdido
    assert s["breakeven"] == pytest.approx(1 / (1 + s["payoff"]))
    assert s["losses"]["by_reason"] == {"SL": 2, "TIEMPO": 1}
    assert s["cost_flips"] == 1        # la de PnL 0 habría ganado antes de su costo


def test_cost_flip_detected():
    s = summarize([tr(-0.5, -0.05, cost=2.0)])
    assert s["cost_flips"] == 1 and s["costs"] == 2.0


def test_empty_is_safe():
    s = summarize([])
    assert s["n"] == 0 and s["win_rate"] is None and s["payoff"] is None and s["pf"] is None


def test_pooled_windows_and_profiles():
    by = {"conservador": [tr(10, 1, exit_days=40)],
          "moderado": [tr(-10, -1, exit_days=10), tr(10, 1, exit_days=0.5)],
          "agresivo": [tr(-20, -1, exit_days=3)]}
    b = balance(by, {"a": "Estrategia A"}, NOW)
    assert list(b) == ["todo", "30d", "7d", "24h"]
    assert (b["todo"]["all"]["wins"]["n"], b["todo"]["all"]["losses"]["n"]) == (2, 2)
    assert b["30d"]["all"]["n"] == 3 and b["7d"]["all"]["n"] == 2 and b["24h"]["all"]["n"] == 1
    assert b["30d"]["profiles"]["conservador"]["n"] == 0
    assert b["todo"]["profiles"]["moderado"]["win_rate"] == pytest.approx(0.5)


def test_feedback_kinds():
    ts = ([tr(30, 1, strategy="buena")] + [tr(-10, -1, strategy="mala") for _ in range(5)]
          + [tr(-5, -0.5, strategy="mala", reason="TIEMPO") for _ in range(3)])
    b = balance({"moderado": ts}, {"buena": "Buena", "mala": "Mala"}, NOW)
    fb = b["todo"]["feedback"]
    kinds = [f["kind"] for f in fb]
    assert kinds[0] == "funciono" and "Buena" in fb[0]["text"]
    assert "no_funciono" in kinds and any("Mala" in f["text"] for f in fb)
    assert any("acertar al menos" in f["text"] for f in fb)
    assert any("por tiempo" in f["text"] for f in fb)
    assert balance({"moderado": []}, {}, NOW)["todo"]["feedback"][0]["kind"] == "mejorar"
