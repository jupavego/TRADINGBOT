"""T111 — A/B de salidas: métricas registradas, emparejado de entradas, condiciones y puerta T49.

Perfiles reales con ideas de BTCUSDT y costos cero (las cuentas se leen a mano), salvo donde se
comprueba justamente el costo de entrada.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.backtest.params import ZERO_COSTS
from eim.paper.ab_conditions import by_condition, day_labels, ex_ante, labeler
from eim.paper.ab_gate import gate_verdicts, strict_oos
from eim.paper.ab_pairs import cut_winners, pair_trades, split
from eim.paper.book import run_profile
from eim.paper.engine import Path, simulate
from eim.paper.feedback import Learner
from eim.paper.ladder import floor_qty, simulate_ladder
from eim.paper.ladder_book import LadderSim
from eim.paper.ladder_metrics import max_dd_r, profile_metrics
from eim.paper.params import PROFILES, ExecParams, spec_for
from eim.validation.criteria import load_criteria
from eim.validation.evidence import Trade
from eim.validation.lineage import Version, Window
from tests.paper.helpers import H1, M15, T0, bar, idea

E = 70_000.0
EP = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
P = {p.id: p for p in PROFILES}
DAY = 86_400_000


def btc(tp: float = E + 2200, t: int = T0, strategy: str = "s"):
    i = idea(side=1, entry=E, sl=E - 1400, tp=tp, t=t, strategy=strategy, syn_bias=0.5)
    return replace(i, symbol="BTCUSDT", htf=1)


def path_of(rows) -> Path:
    return Path([bar(T0 + k * M15, *r) for k, r in enumerate(rows)])


# Sube a +300 (escalón del Moderado), abre por debajo del stop dinámico y luego llega al TP.
CUT = [(E, E + 50, E - 20, E + 30), (E + 30, E + 300, E + 20, E + 250),
       (E + 250, E + 260, E + 100, E + 120), (E + 120, E + 2300, E + 110, E + 2250)] + \
      [(E + 2250, E + 2260, E + 2240, E + 2250)] * 4


def books(pid: str, ideas, rows, k: float | None = None):
    path = path_of(rows)
    sh = [simulate(i, path, EP) for i in ideas]
    pa = P[pid].model_copy(update={"exit_mode": "tp"})
    pb = P[pid] if k is None else P[pid].model_copy(update={"ladder": P[pid].ladder.model_copy(
        update={"first_r": k, "step_r": k / 2})})
    sim = LadderSim(path, EP)
    return run_profile(pa, sh, Learner(sh), 0.004, sim), pb, sim, {o.idea.id: o for o in sh}


def test_ladder_market_entry_pays_the_same_entry_cost_as_the_shadow():
    """BACKLOG T109 (1): la escalera llenaba a mercado con el deslizamiento de SALIDA; el A/B
    exige los mismos costos, así que entra igual que la sombra (mismo llenado, misma comisión)."""
    ep = ExecParams()                                             # costos por defecto, no cero
    path = path_of([(E, E + 900, E - 900, E + 10)] + [(E + 10, E + 20, E, E + 10)] * 3)
    i = btc()
    a = simulate(i, path, ep)
    b = simulate_ladder(i, path, ep, P["moderado"].ladder, 0.07, spec=spec_for("BTCUSDT"))
    assert b.fill == pytest.approx(a.fill) and b.fee_in == a.fee_in
    assert b.fill < E * (1 + 1e-4)          # el término de volatilidad (2,6 % de rango) no entra


def test_metrics_are_counted_from_the_recorded_trades():
    lad = {"level": 2, "nominal_usd": 15.0, "max_float_usd": 18.0, "stop_source": "escalon",
           "stop_history": [{"t": 1}, {"t": 2}], "protected_est_usd": 15.0}
    tr = [{"id": "a", "t": 1, "exit_t": 10, "pnl": 15.5, "r": 0.155, "reason": "SLD",
           "fees": 1.0, "slip": 0.5, "funding": 0.0, "risk_usd": 100.0, "mfe_r": 0.2,
           "ladder": lad},
          {"id": "b", "t": 2, "exit_t": 20, "pnl": -100.0, "r": -1.0, "reason": "SL",
           "fees": 1.0, "slip": 0.5, "funding": 0.5, "risk_usd": 100.0, "mfe_r": 0.05,
           "ladder": {"level": 0, "max_float_usd": 3.0, "stop_history": []}},
          {"id": "c", "t": 3, "exit_t": 30, "pnl": -50.0, "r": -0.5, "reason": "LIQUIDACION",
           "fees": 0.0, "slip": 0.0, "funding": 0.0, "risk_usd": 100.0}]
    opn = [{"upnl": 4.5, "ladder": {"state": "inconsistente"}}]
    curve = [(0, 1000.0), (10, 1015.5), (20, 915.5), (30, 865.5)]
    m = profile_metrics(tr, opn, 1000.0, curve, [{"executed": False}], dd_base="realizado")
    assert (m["n"], m["wins"], m["losses"]) == (3, 1, 2)
    assert m["net_won"] == 15.5 and m["net_lost"] == -150.0 and m["pf"] == pytest.approx(15.5 / 150)
    assert m["capital"]["final_equity"] == pytest.approx(1000 - 134.5 + 4.5)
    assert m["costs"]["total"] == pytest.approx(3.5) and m["costs"]["mean_r"] == pytest.approx(
        (0.015 + 0.02 + 0.0) / 3)
    assert m["exits"]["stop_dinamico"] == 1 and m["exits"]["stop_inicial"] == 1
    assert m["exits"]["liquidacion"] == 1 and m["exits"]["tp"] == 0
    assert m["max_dd_pct"] == pytest.approx(150 / 1015.5)
    assert m["inconsistent"] == 1 and m["violations"] == {"executed": 0, "rejected": 1}
    pr = m["protection"]
    assert pr["activated"] == 1 and pr["levels"] == {"0": 1, "2": 1}
    assert pr["max_level"] == 2 and pr["max_level_r"] == pytest.approx(0.15)
    assert pr["gap_float_vs_final_usd"]["mean"] == pytest.approx((2.5 + 103.0) / 2)
    assert m["gap_mfe_vs_final_usd"]["sum"] == pytest.approx((20 - 15.5) + (5 + 100))


def test_tp_scenario_has_no_protection_block_and_pairs_have_no_account():
    tr = [{"id": k, "t": 1, "exit_t": e, "pnl": 10.0 * r, "r": r, "reason": "TP", "fees": 0.0,
           "slip": 0.0, "funding": 0.0} for k, e, r in (("a", 2, 0.5), ("b", 3, -1.0),
                                                        ("c", 4, -0.5), ("d", 5, 2.0))]
    m = profile_metrics(tr[:1], [], 100.0, [(0, 100.0), (2, 110.0)])
    assert m["protection"] is None and m["exits"]["tp"] == 1 and m["pf"] is None
    assert max_dd_r(tr) == pytest.approx(1.5)                  # +0,5 → −1,0 (pico 0,5, valle −1)
    pair = profile_metrics(tr, [], 100.0, None)
    assert pair["capital"] is None and pair["max_dd_pct"] is None and pair["max_dd_r"] == 1.5


def test_paired_entries_are_identical_and_only_the_exit_differs():
    book_a, pb, sim, by_id = books("moderado", [btc()], CUT)
    (t,) = book_a.trades
    assert t["reason"] == "TP"
    (pr,) = pair_trades(book_a, by_id, pb, sim, 0.004)
    assert pr.same_fill and pr.viable_b and not pr.open_b
    q = floor_qty(t["qty"], 0.001)                       # lo que B puede negociar
    assert q < t["qty"] and pr.b["qty"] == pytest.approx(q) and pr.a["qty"] == pytest.approx(q)
    assert pr.a["pnl"] == pytest.approx(t["pnl"] * q / t["qty"]) and pr.a["r"] == t["r"]
    assert pr.b["reason"] == "SLD" and pr.b["pnl"] == pytest.approx(q * 250)
    c = cut_winners([pr])
    assert (c["a_tp"], c["a_tp_b_less"], c["a_tp_b_lost"]) == (1, 1, 0)
    assert c["given_up_usd"] == pytest.approx(pr.a["pnl"] - pr.b["pnl"])
    a_cl, a_op, b_cl, b_op = split([pr])
    assert len(a_cl) == len(b_cl) == 1 and a_op == b_op == []


def test_entries_the_b_filter_would_drop_are_counted_apart():
    """Con 1 R de umbral el objetivo estimado (R:B 1) no cubre el primer escalón con costos: B no
    la habría abierto. Se marca y queda fuera de la comparación común."""
    i = btc(tp=E + 1400)
    book_a, pb, sim, by_id = books("agresivo", [i], CUT, k=1.0)
    assert [x["id"] for x in book_a.trades] == [i.id]       # A la tomó por su mínimo de abiertas
    (pr,) = pair_trades(book_a, by_id, pb, sim, 0.004)
    assert not pr.viable_b
    assert split([pr])[0] == [] and len(split([pr], viable=False)[0]) == 1
    (ok,) = pair_trades(book_a, by_id, P["agresivo"], sim, 0.004)
    assert ok.viable_b                                        # con 0,075 R sí cabe


def _day(d: int, closes: list[float]) -> list:
    out, px = [], closes[0]
    for k, c in enumerate(closes):
        out.append(bar(T0 // DAY * DAY + d * DAY + k * M15, px, max(px, c), min(px, c), c))
        px = c
    return out


def test_market_conditions_by_day_use_fixed_quantiles():
    up = [100 + k for k in range(96)]                               # tendencia limpia
    zig = [100 + (k % 2) * 0.5 for k in range(96)]                  # lateral
    mid = [100 + (k % 4) * 0.7 + k * 0.05 for k in range(95)] + [130.0]   # brusco al final
    path = Path(_day(0, up) + _day(1, zig) + _day(2, mid))
    lab = day_labels(path)
    days = sorted(lab)
    assert lab[days[0]][0] == "tendencia" and lab[days[1]][0] == "lateral"
    assert lab[days[2]][0] == "intermedio" and lab[days[2]][2] == "brusco"
    assert lab[days[1]][1] == "vol_baja" and lab[days[0]][1] == "vol_alta"
    f = labeler(path)
    t = T0 // DAY * DAY + 5 * H1
    assert f(t) == lab[days[0]] and f(t + 10 * DAY) == ("sin_dato",)
    tr = [{"t": t, "pnl": 2.0, "r": 0.2, "regime": "trend"}, {"t": t, "pnl": -1.0, "r": -0.1}]
    got = by_condition(tr, f)
    assert got["tendencia"]["n"] == 2 and got["tendencia"]["mean_r"] == pytest.approx(0.05)
    ante = by_condition(tr, f, ex_ante)                 # el régimen que se conocía al decidir
    assert set(ante) == {"trend", "sin_dato"} and ante["trend"]["net"] == 2.0


def test_strict_oos_uses_registered_windows_and_drops_unknown_versions():
    a, b, c = (btc(t=T0 + k * DAY, strategy=s) for k, s in ((0, "s"), (5, "s"), (5, "z")))
    a, b = replace(a, version="h1"), replace(b, version="h1")
    by_id = {i.id: simulate(i, path_of(CUT), EP) for i in (a, b, c)}
    v = Version(a.sid, 1, "h1", "s", "1h", T0, None, "auto",
                windows=(Window(T0 - DAY, T0 + DAY, None, "ajuste"),))
    trades = [{"id": i.id} for i in (a, b, c)]
    keep, why = strict_oos(trades, by_id, [v], (), "BTCUSDT")
    assert [x["id"] for x in keep] == [b.id]
    assert why == {"ventana_estrategia_o_salida": 1, "sin_version_registrada": 1}
    keep2, _ = strict_oos(trades, by_id, [v], (Window(T0 + 4 * DAY, T0 + 6 * DAY),), "BTCUSDT")
    assert keep2 == []                                         # la ventana de la salida también


def _trades(rs: list[float]) -> list[Trade]:
    return [Trade(t=T0 + k * DAY, exit_t=T0 + k * DAY + H1, r=r, r_flip=-r, cost_r=0.05,
                  regime="tendencia", origin="backtest") for k, r in enumerate(rs)]


def test_gate_criteria_are_applied_without_relaxing_them():
    crit = load_criteria()
    asof = T0 + 400 * DAY
    few, bad = _trades([0.5] * 30), _trades([-0.4, 0.1] * 30)
    got = {v["id"]: v for v in gate_verdicts([("x|B", few), ("y|B", bad)], {"p|v": 0.5}, crit,
                                             "BTCUSDT", asof)}
    assert got["x|B"]["verdict"] == "EN OBSERVACIÓN" and "V1" in got["x|B"]["reason"]
    assert got["y|B"]["verdict"] == "RECHAZADA" and got["y|B"]["attempts"] == 3
    empty = gate_verdicts([("z|A", [])], {}, crit, "BTCUSDT", asof)[0]
    assert empty["verdict"] == "EN OBSERVACIÓN" and empty["n_oos"] == 0
