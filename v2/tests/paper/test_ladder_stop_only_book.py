"""T109 — En el libro: los tres perfiles salen solo por su stop, y nada más los cierra.

Perfiles reales (Conservador, Moderado, Agresivo) con su escalera en R, ideas de BTCUSDT y costos
cero para que las cuentas se lean a mano. Cubre: ni TP ni tiempo cierran aunque el precio pase el
objetivo estimado y el horizonte; motivos de cierre contados por separado; señales contrarias
como información; una señal nueva o un cambio de versión no tocan la protección; liquidación
simulada con escalera; aprendizaje propio con el peso acotado; BE+ conviviendo con los escalones.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.backtest.params import ZERO_COSTS
from eim.paper.book import run_profile
from eim.paper.engine import Path, simulate
from eim.paper.feedback import Learner
from eim.paper.ladder import simulate_ladder
from eim.paper.ladder_audit import audit_outcome
from eim.paper.ladder_book import LadderRisk, LadderSim
from eim.paper.params import PROFILES, ExecParams, LadderParams, spec_for
from eim.paper.summary import profile_summary
from tests.paper.helpers import H1, M15, T0, bar, idea

E = 70_000.0
EP = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
P = {p.id: p for p in PROFILES}
IDS = ("conservador", "moderado", "agresivo")
CASES = [(pid, side) for pid in IDS for side in (1, -1)]


def btc(side: int = 1, t: int = T0, strategy: str = "s", **kw):
    """SL a 2 % (costo 0,08 R), objetivo estimado a +2 200 de precio, a favor de todo."""
    i = idea(side=side, entry=E, sl=E - side * 1400, tp=E + side * 2200, t=t, strategy=strategy,
             syn_bias=0.5 * side, **kw)
    return replace(i, symbol="BTCUSDT", htf=1)


def mirror(rows, side: int) -> Path:
    """Velas de 15 m desde T0 en precio de un largo; en corto, su espejo respecto a la entrada."""
    f = (lambda x: x) if side > 0 else (lambda x: 2 * E - x)
    return Path([bar(T0 + k * M15, f(o), f(h if side > 0 else lo), f(lo if side > 0 else h), f(c))
                 for k, (o, h, lo, c) in enumerate(rows)])


# Sube por encima del objetivo estimado (+2 200), se queda 30 h (más que el horizonte de 24 h) y
# luego retrocede hasta el stop dinámico.
PAST_TP = ([(E, E + 50, E - 20, E + 30), (E + 40, E + 2400, E + 30, E + 2390)]
           + [(E + 2392, E + 2399, E + 2385, E + 2392)] * 120     # sobre el stop (≈ +1,7 R)
           + [(E + 2392, E + 2395, E + 100, E + 120)])


def book(pid: str, ideas, rows, side: int = 1, p=None):
    path = mirror(rows, side)
    shadows = [simulate(i, path, EP) for i in ideas]
    return run_profile(p or P[pid], shadows, Learner(shadows), 0.004, LadderSim(path, EP))


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_profiles_never_close_by_tp_or_time(pid, side):
    i = btc(side)
    shadow = simulate(i, mirror(PAST_TP, side), EP)
    assert shadow.reason == "TP"                      # la sombra con TP sí habría cerrado ahí
    st = book(pid, [i], PAST_TP, side)
    (t,) = st.trades
    assert t["reason"] == "SLD" and t["tp"] is None and st.violations == []
    assert t["exit_t"] - t["fill_t"] > i.hold_ms      # el horizonte de la idea no cerró nada
    assert (t["exit"] - t["fill"]) * side > 2_000     # se quedó con casi todo el recorrido
    cats = [e["cat"] for e in st.events]
    assert cats == ["orden", "llenada", "sl"] and st.events[0]["tp"] is None
    s = profile_summary(st, Learner([shadow]), [i.sid], T0 + 200 * M15, 0.004)
    assert s["ladder"]["exits"] == {"stop_inicial": 0, "stop_dinamico": 1, "liquidacion": 0,
                                    "salvaguarda": 0, "incidencia_abierta": 0,
                                    "otros_motivos": 0, "rechazados": 0}
    assert s["learning"] == "cierres propios (escalera)" and s["weights"][i.sid]["n"] == 1


@pytest.mark.parametrize("side", [1, -1])
def test_contrary_signal_only_informs(side):
    """Una señal contraria a una posición abierta no la cierra ni le toca el stop: queda anotada en
    su propio evento (`against`) y contada en el resumen."""
    rows = [(E, E + 50, E - 20, E + 30)] + [(E + 30, E + 60, E + 10, E + 40)] * 8
    a = btc(side, strategy="a")
    b = replace(btc(-side, t=T0 + H1, strategy="b"), entry=mirror(rows, side).o[4])
    b = replace(b, sl=b.entry + side * 1400, tp=b.entry - side * 2200)
    alone = book("moderado", [a], rows, side)
    both = book("moderado", [a, b], rows, side)
    assert both.slots[a.id].o.ladder == alone.slots[a.id].o.ladder
    order_b = next(e for e in both.events if e["idea"] == b.id and e["cat"] == "orden")
    assert order_b["against"] == [a.id] and both.contrary == 1
    s = profile_summary(both, Learner([]), [], T0 + 9 * M15, 0.004)
    assert s["ladder"]["contrary_signals"] == 1 and s["ladder"]["exits"]["otros_motivos"] == 0
    cons = book("conservador", [a, b], rows, side)               # sin cobertura: se rechaza
    rej = next(e for e in cons.events if e["idea"] == b.id)
    assert rej["cat"] == "rechazada" and rej["against"] == [a.id] and a.id in cons.slots


@pytest.mark.parametrize("pid", IDS)
def test_new_signal_or_strategy_version_does_not_reset_the_protection(pid):
    rows = PAST_TP[:30]
    a = btc()
    later = btc(t=T0 + 2 * H1)                                   # la misma estrategia, otra vela
    alone, again = book(pid, [a], rows), book(pid, [a, later], rows)
    assert alone.slots[a.id].o.ladder == again.slots[a.id].o.ladder
    assert alone.slots[a.id].o.ladder["level"] > 5
    path, lp, q = mirror(rows, 1), P[pid].ladder, 0.02
    v1 = simulate_ladder(a, path, EP, lp, q, spec=spec_for("BTCUSDT"))
    v2 = simulate_ladder(replace(a, version="otra-huella"), path, EP, lp, q,
                         spec=spec_for("BTCUSDT"))
    assert v1.ladder == v2.ladder and (v1.status, v1.exit) == (v2.status, v2.exit)
    assert book(pid, [a], rows).slots[a.id].o == alone.slots[a.id].o   # recálculo idéntico


def test_one_position_per_bar_and_own_brake_are_only_for_the_control():
    """Los tres perfiles no suman el veto «una por vela y lado» ni el freno propio del control:
    sus entradas siguen como antes de T109 (sus mínimos de abiertas y sus `caps`)."""
    a, b = btc(strategy="a"), btc(strategy="b")
    st = book("moderado", [a, b], PAST_TP[:10])
    assert sum(e["cat"] == "orden" for e in st.events) == 2
    assert not any("duplicada" in e["text"] for e in st.events)
    lp = P["moderado"].ladder
    risk = LadderRisk()
    for k in range(6):
        risk.closed(btc(), -1.0, -100, 10_000 - 100 * k, T0 + k, lp, 10_000)
    assert risk.activations == [] and risk.veto(T0 + 10) is None and risk.consec == 6
    assert P["ppp_btcusdt"].ladder.one_per_bar and P["ppp_btcusdt"].ladder.brake


def test_ladder_liquidation_is_its_own_exit():
    """Un hueco que atraviesa el stop y la liquidación: la cuenta pierde el margen y nada más, con
    motivo propio (T107), también con escalera."""
    rows = [(E, E + 50, E - 20, E + 30), (60_000.0, 60_100.0, 59_000.0, 59_500.0)]
    st = book("agresivo", [btc()], rows)
    (t,) = st.trades
    assert t["reason"] == "LIQUIDACION" and t["pnl"] == pytest.approx(-t["margin"])
    s = profile_summary(st, Learner([]), [], T0 + 3 * M15, 0.004)
    assert s["ladder"]["exits"]["liquidacion"] == 1 and s["ladder"]["exits"]["stop_inicial"] == 0
    assert [e["cat"] for e in st.events][-1] == "liquidacion"


def test_own_learning_weight_is_capped_against_streaks():
    """El Agresivo (`gain` 2,5, `w_max` 3,0) llegaría a 3,0 tras una racha; con la escalera el
    peso queda en `max_weight` = 1,5 (con el tope del 3 % por dirección, es el mismo techo)."""
    agr, risk = P["agresivo"], LadderRisk()
    for k in range(10):
        risk.closed(btc(), 2.0, 200.0, 10_000 + 200 * k, T0 + k, agr.ladder, 10_000)
    j, jc = risk.own("s@1h", "s@1h|sin dato|largo", agr)
    assert j.weight == agr.ladder.max_weight == 1.5 and j.state == "reforzada"
    assert jc.weight <= 1.5
    assert P["ppp_btcusdt"].feedback.w_max == 1.0          # el control nunca sube el tamaño


ONLY_BE = LadderParams(basis="r", first_r=2.0, step_r=0.5, be_with_ladder=True)
BE_EP = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0, est_cost_frac=0.0)


@pytest.mark.parametrize("side", [1, -1])
def test_be_plus_coexists_and_the_best_stop_wins(side):
    """◆3: con un primer escalón lejano (2 R) el BE+ (1 R → +0,1 R) protege antes; en cuanto el
    escalón supera al BE+ manda el escalón. El stop solo sube y el cierre es «SLD»."""
    i = idea(side=side, entry=E, sl=E - side * 500, tp=E + side * 1500)
    spec, q = spec_for("BTCUSDT"), 0.1
    rows = [(E, E + 520, E - 10, E + 500), (E + 500, E + 510, E + 40, E + 45)]
    o = simulate_ladder(i, mirror(rows, side), BE_EP, ONLY_BE, q, spec=spec)
    assert (o.reason, o.ladder["stop_source"], o.ladder["level"]) == ("SLD", "be", 0)
    assert o.exit == pytest.approx(E + side * 50) and audit_outcome(o) == []
    up = rows[:1] + [(E + 500, E + 1100, E + 490, E + 1050), (E + 1050, E + 1060, E + 990, E + 995)]
    o2 = simulate_ladder(i, mirror(up, side), BE_EP, ONLY_BE, q, spec=spec)
    assert [h["source"] for h in o2.ladder["stop_history"]] == ["be", "escalon"]
    assert o2.reason == "SLD" and o2.exit == pytest.approx(E + side * 1000)
    assert audit_outcome(o2) == []
    i15 = replace(i, timeframe="15m")                        # BE+ solo en 1 h y 4 h (T48b)
    o3 = simulate_ladder(i15, mirror(rows, side), BE_EP, ONLY_BE, q, spec=spec)
    assert o3.status == "ABIERTA" and o3.ladder["be"] is None


@pytest.mark.parametrize("pid", IDS)
def test_with_the_real_steps_be_plus_never_beats_the_ladder(pid):
    """Con los umbrales reales (0,075–0,100 R) el escalón ya protege ≈ 0,8 R cuando el BE+ se
    dispara (1 R): BE+ se conserva (◆3), pero en la práctica no interviene."""
    i = idea(entry=E, sl=E - 500, tp=E + 1500)
    rows = [(E, E + 700, E - 10, E + 650), (E + 650, E + 660, E + 40, E + 45)]   # llena a ≈ +60
    o = simulate_ladder(i, mirror(rows, 1), ExecParams(), P[pid].ladder, 0.1,
                        spec=spec_for("BTCUSDT"))
    assert o.ladder["be"]["armed"] and o.ladder["stop_source"] == "escalon"
    assert o.ladder["nominal_usd"] > 30 > (o.ladder["be"]["lock"] - E) * 0.1
