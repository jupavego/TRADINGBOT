"""Auditoría periódica (T159): cifras del libro, palancas, disparadores, diferencias y consola."""

from __future__ import annotations

import csv
import json

import pytest

from eim.analytics.audit import build, kpis, levers, render
from eim.analytics.audit.__main__ import main

NOW = 1_800_000_000_000
COST = json.dumps({"taker_fee": 0.0005, "maker_fee": 0.0002})


def _row(r: float, pnl: float, *, tf="1h", kind="market", fees=4.0, profile="moderado",
         strategy="s1", counts=True, exclusion="", days_ago=1.0, notional=10_000.0) -> dict:
    return {"r": r, "pnl_usdt": pnl, "timeframe": tf, "kind": kind, "fees": fees, "slip": 0.0,
            "funding": 0.0, "notional": notional, "profile": profile, "strategy": strategy,
            "leverage": 5.0, "reason": "SL" if r < 0 else "SLD", "cost_params": COST,
            "counts_as_result": counts, "exclusion": exclusion,
            "exit_t": NOW - int(days_ago * kpis.DAY_MS)}


def _book() -> list[dict]:
    # 30 operaciones: 20 ganan +0,3 R (30 USDT) y 10 pierden −1,1 R (−110 USDT); riesgo 100 USDT.
    rows = [_row(0.3, 30.0) for _ in range(20)] + [_row(-1.1, -110.0) for _ in range(10)]
    rows += [_row(5.0, 500.0, counts=False, exclusion="retro"),
             _row(1.0, 0.0, counts="False", exclusion="sombra")]
    return rows


def test_official_and_stats_follow_phase24_method():
    k = kpis.book_kpis(_book(), NOW)
    a = k["all"]
    assert k["rows_official"] == 30 and k["excluded"] == {"retro": 1, "sombra": 1}
    assert a["win_rate"] == pytest.approx(20 / 30)
    assert a["avg_win_r"] == pytest.approx(0.3) and a["avg_loss_r"] == pytest.approx(-1.1)
    assert a["breakeven_win_rate"] == pytest.approx(1.1 / 1.4)
    assert a["e_r"] == pytest.approx((20 * 0.3 - 11) / 30)
    assert a["cost_r"] == pytest.approx(0.04)          # 4 USDT / 100 USDT de riesgo
    assert a["gross_r"] == pytest.approx(a["e_r"] + 0.04)
    assert a["e_r_ci"][0] < a["e_r"] < a["e_r_ci"][1]
    assert a["beyond_sl_n"] == 10                      # bruto −1,06 < −1,05
    assert a["readable"] and not kpis.stats(kpis.official(_book())[:5])["readable"]


def test_taker_savings_is_entry_fee_difference():
    t = kpis.taker_savings([_row(0.3, 30.0), _row(0.3, 30.0, kind="limit")])
    assert t["n_market"] == 1 and t["share_market"] == 0.5
    assert t["usdt"] == pytest.approx(0.0003 * 10_000)
    assert t["r_per_op"] == pytest.approx(3.0 / 100)


def test_window_and_groups():
    rows = kpis.official(_book())
    rows[0]["exit_t"] = NOW - 10 * kpis.DAY_MS
    assert len(kpis.window(rows, NOW, 7)) == 29
    g = kpis.by(rows, lambda r: r["timeframe"])
    assert list(g) == ["1h"] and g["1h"]["n"] == 30


def test_opportunities_routes_and_signed_impact():
    base = {o["id"]: o for o in levers.opportunities(kpis.book_kpis(_book(), NOW))}
    assert base["sin_bruto"]["route"] == "cerrada"
    assert base["equilibrio"]["route"].startswith("cerrada")
    rows = _book() + [_row(0.2, 20.0, tf="15m", fees=20.0) for _ in range(25)]
    k = kpis.book_kpis(rows, NOW)
    opps = {o["id"]: o for o in levers.opportunities(k)}
    caro = opps["marco_caro_15m"]                      # costo 0,2 R ≥ 0,15, pero gana
    assert caro["impact_usdt"] < 0 and "menos malo" in caro["evidence"]
    assert opps["maker"]["impact_usdt"] > 0
    order = [o["impact_usdt"] or 0 for o in levers.opportunities(k)]
    assert order == sorted(order, reverse=True)


def test_losing_strategy_needs_user_and_variant_waits_for_sample():
    rows = [_row(-1.0, -100.0, strategy="mala") for _ in range(28)]
    rows += [_row(0.5, 50.0, strategy="mala") for _ in range(2)]
    k = kpis.book_kpis(rows, NOW)
    o = {x["id"]: x for x in levers.opportunities(k)}["estrategia_mala"]
    assert o["route"].startswith("◆") and o["impact_usdt"] > 0
    var = build.variant_block(rows, rows[:5])
    assert levers.variant_vs_official(k, var)["route"] == "esperar"
    var = build.variant_block(rows, rows)
    assert levers.variant_vs_official(k, var)["route"].startswith("◆")


def test_calibration_findings():
    c = {"brier_skill": -0.01, "directional": {"n": 500, "accuracy": 0.41}, "n_effective": 22,
         "mean_prob": {"bull": 0.27, "bear": 0.28}, "realized_freq": {"bull": 0.15, "bear": 0.30}}
    ids = {o["id"] for o in levers.calibration_opps(c)}
    assert ids == {"calib_sin_skill", "calib_sesgo_bull"}
    assert levers.calibration_opps({"brier_skill": 0.05}) == []


def test_triggers_fire_and_near():
    t = {x["id"]: x for x in levers.triggers({"BTCUSDT": 0.045, "ETHUSDT": 0.035, "X": None},
                                             300.0, 0.995)}
    assert t["funding_BTCUSDT"]["fired"] and not t["funding_BTCUSDT"]["near"]
    assert t["funding_ETHUSDT"]["near"] and not t["funding_ETHUSDT"]["fired"]
    assert not t["funding_X"]["fired"] and "sin medir" in t["funding_X"]["text"]
    assert t["l2_un_ano"]["near"] and not t["hft_calidad"]["fired"]
    assert {x["id"]: x for x in levers.triggers({}, None, 0.8)}["hft_calidad"]["fired"]


def test_deltas_against_previous_audit():
    first = build.build(_book(), NOW, "2026-11-11T00:00:00Z")
    assert first["deltas"] == {"previous": None}
    more = _book() + [_row(0.3, 30.0) for _ in range(10)]
    second = build.build(more, NOW, "2026-11-18T00:00:00Z", prev=first,
                         funding={"BTCUSDT": 0.05})
    d = second["deltas"]
    assert d["previous"] == "2026-11-11T00:00:00Z"
    assert d["metrics"]["all.n"]["delta"] == 10
    assert d["triggers_new"] == ["funding_BTCUSDT"]


def test_render_markdown_and_console():
    a = build.build(_book(), NOW, "2026-11-11T00:00:00Z", funding={"BTCUSDT": 0.035},
                    calibration={"n_evaluated": 10, "brier_skill": -0.1, "curve": [1]})
    a["paths"] = {"md": "x.md", "json": "x.json"}
    md = render.markdown(a)
    assert "SIMULADO" in md and "## 2. Oportunidades" in md and "cerca" in md
    assert "curve" not in a["calibration"]
    out = render.console(a)
    assert out.splitlines()[0].startswith("AUDITORÍA") and len(out.splitlines()) < 30
    assert "PRIMERA AUDITORÍA" in out


def test_cli_offline_writes_reports_and_compares(tmp_path, capsys):
    led = tmp_path / "libro.csv"
    rows = _book()
    with led.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    out = tmp_path / "audit"
    (out).mkdir()
    (out / "audit_2000-01-01.json").write_text(json.dumps(
        build.build(rows[:10], NOW, "2000-01-01T00:00:00Z")), encoding="utf-8")
    assert main(["--ledger", str(led), "--sin-red", "--out", str(out),
                 "--data-dir", str(tmp_path / "nada")]) == 0
    text = capsys.readouterr().out
    assert "DESDE 2000-01-01" in text
    files = sorted(p.name for p in out.iterdir())
    assert len(files) == 3 and any(f.endswith(".md") for f in files)
