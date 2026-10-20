"""PPP en el libro: entrada, tamaño, independencia de los otros perfiles, auditoría y métricas."""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.backtest.params import ZERO_COSTS
from eim.paper.book import ProfileState, Slot, _close, run_profile
from eim.paper.engine import Outcome, Path, simulate
from eim.paper.feedback import Learner
from eim.paper.ladder_book import LadderSim, viability
from eim.paper.ladder_stats import ladder_stats
from eim.paper.params import PPP_ID, PROFILES, ExecParams
from eim.paper.summary import profile_summary
from tests.paper.helpers import H1, M15, T0, bar, idea

PPP = next(p for p in PROFILES if p.id == PPP_ID)
MOD = next(p for p in PROFILES if p.id == "moderado")
E = 70_000.0
EP = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)


def btc_idea(**kw):
    """SL a 2 % (costo 0,08 R), objetivo estimado 2 200 USDT de precio, a favor de tendencia."""
    return replace(idea(entry=E, sl=E - 1400, tp=E + 2200, t=T0, syn_bias=0.5, **kw),
                   symbol="BTCUSDT", htf=1)


def path_of(bars):
    return Path([bar(T0 + k * M15, *b) for k, b in enumerate(bars)])


# +300 USDT de precio = +10 USDT por 0,035 BTC: sube, el SL sube y luego retrocede hasta tocarlo
UP = [(E, E + 50, E - 20, E + 30), (E + 40, E + 700, E + 30, E + 650),
      (E + 660, E + 900, E + 640, E + 880), (E + 880, E + 890, E + 100, E + 150)]


def build(bars, i=None, p=PPP):
    i = i or btc_idea()
    path = path_of(bars)
    shadow = simulate(i, path, EP)
    return run_profile(p, [shadow], Learner([shadow]), 0.004, LadderSim(path, EP))


def test_entry_sizing_and_ladder_close_in_book():
    st = build(UP)
    (t,) = st.trades
    assert t["reason"] == "SLD" and t["tp"] is None and st.violations == []
    assert t["qty"] == pytest.approx(0.035)          # 50 USDT de riesgo / 1 400, al paso de 0,001
    assert t["pnl"] == pytest.approx(t["qty"] * (t["exit"] - t["fill"]))
    assert t["pnl"] > 10 and t["ladder"]["level"] >= 2
    assert st.equity == pytest.approx(10_000 + t["pnl"])
    cats = [e["cat"] for e in st.events]
    assert cats == ["orden", "llenada", "sl"] and "dinámico" in st.events[-1]["text"]
    assert st.events[0]["tp"] is None                # el plan no declara un TP final


def test_does_not_touch_other_profiles():
    path = path_of(UP)
    shadow = simulate(btc_idea(), path, EP)
    before = run_profile(MOD, [shadow], Learner([shadow]), 0.004)
    after = run_profile(MOD, [shadow], Learner([shadow]), 0.004, LadderSim(path, EP))
    assert before.trades == after.trades and before.events == after.events
    assert before.equity == after.equity


def test_other_symbol_ignored_and_requires_sim():
    path = path_of(UP)
    i = replace(btc_idea(), symbol="ETHUSDT")
    sh = simulate(i, path, EP)
    assert run_profile(PPP, [sh], Learner([sh]), 0.005, LadderSim(path, EP)).events == []
    with pytest.raises(ValueError):
        run_profile(PPP, [sh], Learner([sh]), 0.005)


def test_vetoes_unviable_and_duplicates():
    # con capital pequeño el objetivo estimado no cubre el primer escalón → no es oportunidad
    assert viability(PPP, btc_idea(), 10_000.0) is None
    assert "primer escalón" in viability(PPP, btc_idea(), 1_000.0)
    path = path_of(UP)
    a, b = btc_idea(), replace(btc_idea(), id="otra", strategy="otra")
    sa, sb = simulate(a, path, EP), simulate(b, path, EP)
    st = run_profile(PPP, [sa, sb], Learner([sa, sb]), 0.004, LadderSim(path, EP))
    assert sum(e["cat"] == "orden" for e in st.events) == 1
    assert any("duplicada" in e["text"] for e in st.events if e["cat"] == "rechazada")


def test_no_size_up_after_loss():
    losing = [(E, E + 20, E - 1500, E - 1450)]
    st = build(losing)
    assert st.trades[0]["reason"] == "SL" and st.trades[0]["pnl"] == pytest.approx(-49.0, abs=1)
    assert st.trades[0]["weight"] == 1.0


def test_restart_recomputation_is_identical():
    a, b = build(UP), build(UP)
    assert a.trades == b.trades and a.events == b.events and a.equity == b.equity
    open_ = build(UP[:3])
    (slot,) = open_.slots.values()
    again = build(UP[:3]).slots[slot.o.idea.id]
    assert slot.o.ladder == again.o.ladder and slot.o.ladder["level"] >= 2   # no pierde escalones


def test_forged_time_or_tp_close_is_a_violation_not_a_result():
    st = build(UP)
    t = st.trades[0]
    o = simulate(btc_idea(), path_of(UP), EP)
    ladder_o = replace(o, status="CERRADA", reason="TIEMPO", fill_t=T0, fill=E, exit_t=T0 + H1,
                       exit=E + 500, ladder={"level": 0, "stop": E - 1400, "stop_history": [],
                                             "incident": ""})
    fresh = ProfileState(p=PPP, equity=10_000.0)
    fresh.slots["x"] = Slot(replace(ladder_o, idea=replace(o.idea, id="x")), 0.035, 3, 800.0, 1.0,
                            50.0, filled=True)
    fresh.used = 800.0
    _close(fresh, replace(ladder_o, idea=replace(o.idea, id="x")))
    assert fresh.trades == [] and fresh.equity == 10_000.0 and fresh.used == 0.0
    assert fresh.violations and "tiempo" in fresh.violations[0]["reasons"][0]
    assert fresh.events[-1]["cat"] == "violacion" and t["reason"] == "SLD"


def test_summary_and_metrics():
    st = build(UP)
    s = profile_summary(st, Learner([]), [], T0 + 5 * H1, 0.004)
    lad = s["ladder"]
    assert lad["n"] == 1 and lad["closed_dynamic_sl"] == 1 and lad["closed_initial_sl"] == 0
    assert lad["reached"][0] == {"level": 1, "nominal": 10.0, "reached": 1}
    assert lad["violations"] == 0 and lad["avg_max_float_usd"] >= lad["avg_realized_usd"]
    assert lad["by_side"]["LONG"]["n"] == 1 and lad["avg_gap_max_vs_realized_usd"] >= 0
    assert s["params"]["exit_mode"] == "ladder" and s["params"]["ladder"]["first_usdt"] == 10.0
    open_s = profile_summary(build(UP[:3]), Learner([]), [], T0 + 5 * H1, 0.004)
    (pos,) = open_s["positions"]
    assert pos["tp"] is None and pos["expire_t"] is None and pos["sl"] == pos["ladder"]["stop"]
    assert "ladder" not in profile_summary(build(UP, p=MOD), Learner([]), [], T0, 0.004)


def test_ladder_stats_counts_levels_and_streaks():
    def tr(level, pnl, reason, k, side=1):
        return {"ladder": {"level": level, "max_float_usd": pnl + 3, "elapsed_ms": 2 * H1,
                           "protected_est_usd": pnl}, "pnl": pnl, "reason": reason, "side": side,
                "regime": "alcista", "fill_t": T0 + k * H1, "exit_t": T0 + k * H1 + 1,
                "sid": "s@1h"}
    ts = [tr(0, -50, "SL", 0), tr(0, -50, "SL", 1), tr(3, 20, "SLD", 2), tr(1, 10, "SLD", 3, -1)]
    s = ladder_stats(ts, [{"elapsed_h": 100}], 0, 0, 10.0, 5.0)
    assert [x["reached"] for x in s["reached"]] == [2, 1, 1]
    assert s["closed_initial_sl"] == 2 and s["closed_dynamic_sl"] == 2
    assert s["max_consecutive_losses"] == 2 and s["long_open_positions"] == 1
    assert s["by_max_level"]["3"]["pullbacks"] == 1 and s["by_side"]["SHORT"]["n"] == 1
    assert s["avg_hours"] == pytest.approx(2.0) and s["duration"] == {"< 4 h": 4}
    assert isinstance(Outcome(idea(), "PENDIENTE").ladder, type(None))
