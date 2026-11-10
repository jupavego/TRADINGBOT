"""PPP en el libro: entrada, tamaño, independencia de los otros perfiles, auditoría y métricas."""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.backtest.params import ZERO_COSTS
from eim.paper.book import ProfileState, Slot, _close, run_profile
from eim.paper.engine import Outcome, Path, simulate
from eim.paper.feedback import Learner
from eim.paper.ladder_book import LadderRisk, LadderSim, viability
from eim.paper.ladder_stats import ladder_stats
from eim.paper.params import PPP_ID, PROFILES, ExecParams, LadderParams
from eim.paper.summary import profile_summary
from tests.paper.helpers import H1, M15, T0, bar, idea, tp_mode

PPP = next(p for p in PROFILES if p.id == PPP_ID)
MOD_TP = tp_mode(next(p for p in PROFILES if p.id == "moderado"))   # salida TP (A/B, T109)
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
    """Un perfil con la salida TP (el modo A/B que sigue existiendo) ignora el camino de la
    escalera: mismos trades y eventos con y sin él."""
    path = path_of(UP)
    shadow = simulate(btc_idea(), path, EP)
    before = run_profile(MOD_TP, [shadow], Learner([shadow]), 0.004)
    after = run_profile(MOD_TP, [shadow], Learner([shadow]), 0.004, LadderSim(path, EP))
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


def _forged(reason: str, ladder: dict) -> tuple[ProfileState, Outcome]:
    """Un perfil con una posición abierta y un cierre «fabricado» con `reason`."""
    o = simulate(btc_idea(), path_of(UP), EP)
    forged = replace(o, status="CERRADA", reason=reason, fill_t=T0, fill=E, exit_t=T0 + H1,
                     exit=E + 500, idea=replace(o.idea, id="x"), ladder=ladder)
    st = ProfileState(p=PPP, equity=10_000.0)
    st.slots["x"] = Slot(forged, 0.035, 3, 800.0, 1.0, 50.0, filled=True)
    st.used = 800.0
    _close(st, forged)
    return st, forged


@pytest.mark.parametrize("reason", ["TIEMPO", "TP", "BE", "NIVEL", "AGENTE", "RETROCESO",
                                    "MANUAL", "OTRO"])
def test_forged_close_by_anything_but_the_stop_is_rejected_not_executed(reason):
    """T109: un cierre que no es del stop (ni liquidación ni salvaguarda) se registra como
    violación y NO se ejecuta: la posición sigue abierta con su stop y el dinero no se mueve
    (hasta T107 se ejecutaba y se contabilizaba; antes de T107 su PnL desaparecía)."""
    st, _ = _forged(reason, {"level": 0, "stop": E - 1400, "stop_history": [], "incident": "",
                             "elapsed_ms": H1})
    assert st.trades == [] and st.equity == 10_000.0 and st.used == 800.0
    (slot,) = st.slots.values()
    assert slot.o.status == "ABIERTA" and slot.o.exit is None
    assert slot.o.ladder["rejected_close"] and slot.o.ladder["stop"] == E - 1400
    (v,) = st.violations
    assert v["executed"] is False and v["reasons"]
    assert [e["cat"] for e in st.events] == ["violacion"]
    assert "no se ejecuta" in st.events[0]["text"]
    s = profile_summary(st, Learner([]), [], T0 + 5 * H1, 0.004)
    assert s["ladder"]["exits"]["rechazados"] == 1 and s["counts"]["violations"] == 1
    assert s["positions"][0]["sl"] == E - 1400              # el stop vigente sigue mandando


def test_stop_close_with_tampered_history_is_executed_accounted_and_audited():
    """Si el precio tocó el stop el cierre ocurre, pero un historial anómalo queda auditado y su
    PnL entra en la cuenta (el dinero nunca desaparece, T106 A5)."""
    bad_hist = [{"t": T0, "level": 1, "nominal": 10.0, "stop": E - 2000, "max_float": 11.0,
                 "source": "escalon"}]                         # «protección» bajo el SL inicial
    st, forged = _forged("SLD", {"level": 1, "stop": E + 500, "stop_history": bad_hist,
                                 "incident": "", "nominal_usd": 10.0})
    (t,) = st.trades
    assert t["violation"] and t["pnl"] == pytest.approx(t["notional"] * forged.net) != 0
    assert st.equity == pytest.approx(10_000.0 + t["pnl"]) and st.used == 0.0
    assert st.violations[0]["executed"] is True
    assert [e["cat"] for e in st.events] == ["violacion", "sl"]


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
    assert "ladder" not in profile_summary(build(UP, p=MOD_TP), Learner([]), [], T0, 0.004)


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


def _losing_run(n_ideas: int):
    """Una idea por hora; cada una pierde en su propia vela (SL a 2 %), luego el precio vuelve."""
    bars, shadows = [], []
    for _ in range(n_ideas):
        bars += [(E, E + 20, E - 1500, E - 1450), (E, E + 10, E - 10, E), (E, E + 10, E - 10, E),
                 (E, E + 10, E - 10, E)]
    path = path_of(bars)
    for k in range(n_ideas):
        i = replace(btc_idea(), id=f"L{k}", strategy=f"s{k}", t=T0 + k * H1)
        shadows.append(simulate(i, path, EP))
    return run_profile(PPP, shadows, Learner(shadows), 0.004, LadderSim(path, EP))


def test_brake_after_consecutive_losses_blocks_new_entries_only():
    st = _losing_run(5)
    assert [t["reason"] for t in st.trades] == ["SL"] * 4          # la 5.ª no entra
    assert st.lrisk.activations and "4 pérdidas seguidas" in st.lrisk.activations[0]["reason"]
    assert any("entradas en pausa" in e["text"] for e in st.events if e["cat"] == "rechazada")
    assert any("freno de entradas" in e["text"] for e in st.events if e["cat"] == "aprendizaje")
    assert st.violations == [] and st.slots == {}                    # no cerró nada por el freno


def test_drawdown_brake_and_resume():
    lp, risk = LadderParams(max_consec_losses=99, max_drawdown=0.05, pause_hours=2), LadderRisk()
    i = btc_idea()
    assert risk.closed(i, -1.0, -300, 9_700, T0, lp, 10_000) is None
    why = risk.closed(i, -1.0, -250, 9_450, T0 + H1, lp, 10_000)
    assert why and "drawdown" in why and risk.veto(T0 + 2 * H1)
    assert risk.veto(T0 + 4 * H1) is None                           # reanuda tras la pausa
    assert risk.peak == 9_450 and risk.consec == 0                  # y parte del capital actual


def test_ladder_learns_from_its_own_closes():
    r = LadderRisk()
    for k in range(10):
        r.closed(replace(btc_idea(), strategy="mala"), -1.0, -10, 9_990, T0 + k, LadderParams(
            max_consec_losses=99, max_drawdown=0.9), 10_000)
    j, jc = r.own("mala@1h", "mala@1h|sin dato|largo", PPP)
    assert j.state == "pausa" and j.weight == 0 and jc.state == "pausa"
    assert r.own("otra@1h", "x", PPP)[0].state == "observacion"     # lo demás sigue con peso 1
