"""Comparación de dos corridas en papel con la contabilidad oficial (cierre de T143)."""

from __future__ import annotations

import pytest

from eim.paper import run_compare as rc

T0, T1 = 1_000_000, 2_000_000


def row(idea: str, *, profile: str = "moderado", tf: str = "1h", kind: str = "market",
        r: float = 0.1, pnl: float = 10.0, fees: float = 1.0, slip: float = 1.0,
        opened: int = T0 + 10, exit_t: int = T0 + 500, reason: str = "SLD",
        fill: float = 100.0, qty: float = 1.0, **kw) -> dict:
    base = {"ledger_id": f"{profile}-{idea}-{kind}", "scope": "perfil", "origin": "vivo",
            "profile": profile, "symbol": "BTCUSDT", "idea_id": idea, "timeframe": tf,
            "kind": kind, "side": "1", "opened_t": str(opened), "fill_t": str(opened),
            "exit_t": str(exit_t), "fill": str(fill), "sl": str(fill * 0.99), "r": str(r),
            "pnl_usdt": str(pnl), "fees": str(fees), "slip": str(slip), "funding": "0",
            "notional": str(fill * qty), "qty": str(qty), "weight": "1.0", "retro": "False",
            "reason": reason, "capital_before": "1000"}
    return {**base, **{k: str(v) for k, v in kw.items()}}


def test_window_needs_opening_and_closing_inside() -> None:
    rows = [row("a"), row("antes", opened=T0 - 1), row("tarde", exit_t=T1),
            row("abierta", exit_t="")]
    assert [r["idea_id"] for r in rc.in_window(rows, T0, T1)] == ["a"]


def test_window_applies_the_official_universe() -> None:
    rows = [row("a"), row("retro", retro="True"), row("sombra", scope="sombra"),
            row("backtest", origin="backtest"), row("sin_peso", weight="0")]
    assert [r["idea_id"] for r in rc.in_window(rows, T0, T1)] == ["a"]


def test_cost_and_gross_in_r_follow_the_diagnosis() -> None:
    # riesgo = |pnl| / |r| = 100 USDT; costo 2 USDT → 0,02 R; bruto = neto + costo
    b = rc.block([row("a", r=0.1, pnl=10.0, fees=1.0, slip=1.0)])
    assert b["cost_r"] == pytest.approx(0.02)
    assert b["gross_r"] == pytest.approx(0.12)
    assert b["net_r"] == pytest.approx(0.1)


def test_stats_declare_their_uncertainty() -> None:
    s = rc.stats([1.0, 3.0, None])
    assert s["n"] == 2 and s["mean"] == pytest.approx(2.0)
    assert s["ci95"][0] < 2.0 < s["ci95"][1]
    assert rc.stats([])["mean"] is None


def test_paired_separates_common_from_composition() -> None:
    a = [row("x", r=0.1), row("solo_a", r=-1.0, reason="SL")]
    b = [row("x", r=0.12, kind="limit", fees=0.5), row("solo_b", r=0.3)]
    p = rc.paired(a, b)
    assert p["all"]["n"] == 1
    assert p["all"]["d_net_r"]["mean"] == pytest.approx(0.02)
    assert p["all"]["kinds"] == {"market→limit": 1}
    assert p["only_a"]["n"] == 1 and p["only_a"]["net_r"] == pytest.approx(-1.0)
    assert p["only_b"]["n"] == 1 and p["only_b"]["net_r"] == pytest.approx(0.3)


def test_pairs_are_per_profile_not_per_idea() -> None:
    a = [row("x", profile="moderado")]
    b = [row("x", profile="agresivo")]
    p = rc.paired(a, b)
    assert p["all"]["n"] == 0 and p["only_a"]["n"] == 1 and p["only_b"]["n"] == 1


def test_converted_splits_same_exit_from_other_exit() -> None:
    a = [row("x", r=0.10, fees=1.0), row("y", r=0.14, reason="SLD")]
    b = [row("x", r=0.12, kind="limit", fees=0.7),
         row("y", r=-1.1, kind="limit", reason="SL", pnl=-110.0)]
    c = rc.paired(a, b)["converted"]
    assert c["n"] == 2
    assert c["same_exit"]["n"] == 1
    assert c["same_exit"]["d_net_r"]["mean"] == pytest.approx(0.02)
    assert [o["reason"] for o in c["other_exit"]] == [["SLD", "SL"]]
    assert c["fees_bps"][0] > c["fees_bps"][1]


def test_gate_check_flags_cells_over_the_threshold() -> None:
    kept = [row("a", profile="agresivo", tf="15m", fees=10.0, slip=8.0),   # 0,18 R
            row("b", profile="moderado", tf="4h", fees=3.0, slip=3.0)]     # 0,06 R
    g = {c["cell"]: c for c in rc.gate_check(kept, 0.15)}
    assert g["agresivo·15m"]["over"] is True
    assert g["moderado·4h"]["over"] is False


def test_compare_reports_both_books_with_their_digest() -> None:
    a = [row("x"), row("y", r=-1.0, pnl=-100.0, reason="SL")]
    b = [row("x", kind="limit")]
    res = rc.compare(a, b, T0, T1)
    assert res["a"]["official"]["n"] == 2 and res["b"]["official"]["n"] == 1
    assert res["a"]["official"]["counted_digest"] != res["b"]["official"]["counted_digest"]
    assert res["window"]["universe"] == "libro_perfiles"
    assert set(res["a"]["by_timeframe"]) == {"1h"}


def test_paired_difference_is_the_same_as_the_t175_audit() -> None:
    from eim.analytics.audit import build

    a = [row("x", r=0.1), row("y", r=-1.0, pnl=-100.0, reason="SL"), row("z", r=0.2)]
    b = [row("x", r=0.12, kind="limit"), row("y", r=-1.05, pnl=-105.0, reason="SL"),
         row("w", r=0.3)]
    assert rc.paired(a, b)["all"]["d_net_r"]["mean"] == pytest.approx(build.paired(a, b)["d_r"])
