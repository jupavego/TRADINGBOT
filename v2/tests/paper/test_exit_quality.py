"""T130 — Calidad de la salida y A/B en vivo frente a la sombra (función pura)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from eim.paper.exit_cli import render
from eim.paper.exit_quality import desk_exit_quality, exit_quality


def _t(iid: str, pnl: float, cost: float, reason: str, risk: float = 100.0) -> dict:
    return {"id": iid, "pnl": pnl, "r": pnl / risk, "fees": cost, "slip": 0.0, "funding": 0.0,
            "risk_usd": risk, "reason": reason, "exit_t": len(iid), "mfe_r": None}


# nueve ganadoras chicas y una pérdida completa: el patrón de la escalera (T129 §1.4)
TRADES = [_t(f"w{k}", 10.0, 12.0, "SLD") for k in range(9)] + [_t("l", -114.0, 14.0, "SL")]


def test_breakeven_cost_and_gross_expectancy():
    q = exit_quality(TRADES, {})
    assert q["n"] == 10 and q["win_rate"] == pytest.approx(0.9)
    assert q["avg_win_r"] == pytest.approx(0.10) and q["avg_loss_r"] == pytest.approx(-1.14)
    assert q["breakeven_win_rate"] == pytest.approx(1.14 / 1.24)      # ≈ 91,9 % para empatar
    assert q["pf"] == pytest.approx(90 / 114)
    assert q["cost_mean_r"] == pytest.approx((9 * 0.12 + 0.14) / 10)
    assert q["gross_expectancy_r"] == pytest.approx((9 * 0.22 - 1.0) / 10)
    assert q["costs_vs_gross_won"] == pytest.approx((9 * 12 + 14) / (9 * 22))
    assert q["by_exit"]["SL"] == {"n": 1, "mean_r": pytest.approx(-1.14)}
    assert q["vs_shadow"] is None


def test_pairs_with_the_shadow_split_by_shadow_exit():
    sh = {f"w{k}": SimpleNamespace(status="CERRADA", r=1.5, reason="TP") for k in range(3)}
    sh |= {f"w{k}": SimpleNamespace(status="CERRADA", r=-1.1, reason="SL") for k in range(3, 6)}
    sh["w6"] = SimpleNamespace(status="ABIERTA", r=None, reason="")   # sin cerrar: no empareja
    p = exit_quality(TRADES, sh)["vs_shadow"]
    assert p["n"] == 6 and p["shadow_exits"] == {"TP": 3, "SL": 3}
    assert p["book_r"] == pytest.approx(0.10) and p["shadow_r"] == pytest.approx(0.2)
    assert p["delta_r"] == pytest.approx(-0.1)
    assert p["when_shadow_tp"] == {"n": 3, "book_r": pytest.approx(0.1),
                                   "shadow_r": pytest.approx(1.5)}
    assert p["when_shadow_sl"]["shadow_r"] == pytest.approx(-1.1)


def test_desk_wrapper_and_render_say_mode_and_dependence():
    books = {"agresivo": SimpleNamespace(trades=TRADES), "vacio": SimpleNamespace(trades=[])}
    out = desk_exit_quality(books, [SimpleNamespace(idea=SimpleNamespace(id="w0"),
                                                    status="CERRADA", r=1.5, reason="TP")])
    assert out["agresivo"]["vs_shadow"]["n"] == 1 and out["vacio"]["n"] == 0
    text = "\n".join(render({"mode": "SIMULADO", "symbol": "BTCUSDT", "snapshot": None,
                             "profiles": out}))
    assert text.startswith("Modo: SIMULADO") and "equilibrio 91.9%" in text
    assert "no son independientes" in text
