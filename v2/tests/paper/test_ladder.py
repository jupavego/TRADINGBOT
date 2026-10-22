"""Protección progresiva PPP: fórmulas, escalones, LONG/SHORT, costos, incidencias y auditoría.

Precios a escala BTC con `qty` = 0,1 BTC: cada 100 USDT de precio = 10 USDT de beneficio.
Con costos cero el SL del escalón L está exactamente en `entrada ± L / qty`.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace

import pytest

from eim.backtest.params import ZERO_COSTS
from eim.paper.engine import Outcome, Path, simulate
from eim.paper.ladder import (
    LadderCosts,
    level_of,
    net_usd,
    nominal,
    protect_price,
    simulate_ladder,
)
from eim.paper.ladder_audit import audit_outcome, check_close_request
from eim.paper.params import ExecParams, LadderParams, spec_for
from tests.paper.helpers import M15, T0, bar, idea

E = 70_000.0
QTY = 0.1
ZERO = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
LP = LadderParams()
SPEC = spec_for("BTCUSDT")   # tick y paso de BTCUSDT (T108)
STEPS = LP.steps(0.0)        # basis "usdt": 10 y 5, sin depender del riesgo


def path_of(bars: list[tuple[float, float, float, float]], mirror: bool = False) -> Path:
    """Velas de 15 m desde T0; `mirror` las refleja respecto a la entrada (largo ↔ corto)."""
    f = (lambda x: 2 * E - x) if mirror else (lambda x: x)
    return Path([bar(T0 + i * M15, f(o), f(lo if mirror else h), f(h if mirror else lo), f(c))
                 for i, (o, h, lo, c) in enumerate(bars)])


def run(bars, side: int = 1, ep: ExecParams = ZERO, qty: float = QTY, **kw) -> Outcome:
    sl = E - 500 if side > 0 else E + 500
    i = idea(side=side, entry=E, sl=sl, tp=E + side * 1500, **kw)
    return simulate_ladder(i, path_of(bars, mirror=side < 0), ep, LP, qty, spec=SPEC)


def usd(o: Outcome, qty: float = QTY) -> float:
    return o.net * o.fill * qty


# Camino base: +10 en la vela 0; +16 en la 1 (escalón 15); +26 en la 2 (salta a 25); cierra en la 3.
RISE = [(E, E + 100, E - 10, E + 90), (E + 120, E + 160, E + 110, E + 150),
        (E + 160, E + 260, E + 150.5, E + 250)]


# --- fórmulas -------------------------------------------------------------------------------
def test_levels_and_nominal():
    assert [level_of(x, *STEPS) for x in (0, 9.99, 10, 14.99, 15, 20.5, 49.99, 50)] == [
        0, 0, 1, 1, 2, 3, 8, 9]
    assert [nominal(n, *STEPS) for n in range(0, 4)] == [0.0, 10.0, 15.0, 20.0]


def test_protect_price_zero_costs_exact():
    c = LadderCosts(0, 0, 0, 0)
    assert protect_price(1, QTY, E, 10, 0, c, 0.1) == pytest.approx(E + 100)
    assert protect_price(-1, QTY, E, 25, 0, c, 0.1) == pytest.approx(E - 250)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("level", [10.0, 15.0, 20.0, 55.0])
def test_protect_price_nets_the_level_with_costs(side, level):
    c = LadderCosts(0.0005, 0.0001, 0.0005, 0.0001)
    for funding in (0.0, 0.0003, -0.0003):
        p = protect_price(side, QTY, E, level, funding, c, 0.1)
        assert net_usd(side, QTY, E, p, funding, c) >= level - 1e-9        # nunca por debajo
        worse = p - side * 0.1                                              # un tick menos
        assert net_usd(side, QTY, E, worse, funding, c) < level            # y es el más justo
        assert (p - E) * side > 0                       # siempre en ganancia: nunca break-even


def test_costs_raise_the_protection_price():
    free = protect_price(1, QTY, E, 10, 0, LadderCosts(0, 0, 0, 0), 0.1)
    paid = protect_price(1, QTY, E, 10, 0, LadderCosts(0.0005, 0, 0.0005, 0.0001), 0.1)
    assert paid > free + 60                      # ≈ 0,11 % de 70 000 en comisiones por 0,1 BTC


def test_net_matches_engine_accounting():
    """`net_usd` es la misma contabilidad que `Outcome.net` del motor (entrada, salida, funding)."""
    i = idea(entry=E, sl=E - 500, tp=E + 1500)
    ep = ExecParams().model_copy(update={"be_trigger_r": 0.0})
    o = simulate(i, path_of([(E, E + 300, E - 10, E + 250), (E + 250, E + 260, E + 240, E + 250)]),
                 ep)
    assert o.status == "ABIERTA"
    c = LadderCosts(fee_in=o.fee_in, slip_in=o.slip, fee_out=0.0, slip_out=0.0)
    assert net_usd(1, QTY, o.fill, o.mark, o.funding, c) == pytest.approx(QTY * o.fill * o.net)


# --- escenarios de la estrategia ---------------------------------------------------------
def test_1_initial_sl_before_first_step():
    o = run([(E, E + 50, E - 10, E + 20), (E + 20, E + 30, E - 600, E - 550)])
    assert (o.status, o.reason) == ("CERRADA", "SL") and o.ladder["level"] == 0
    assert o.exit == E - 500 and usd(o) == pytest.approx(-50.0)
    assert o.ladder["state"] == "cerrada_sl_inicial" and audit_outcome(o) == []


def test_2_first_step_activates_protection_and_then_stop():
    o = run([(E, E + 100, E - 10, E + 90), (E + 150, E + 160, E + 90, E + 95)])
    assert (o.status, o.reason) == ("CERRADA", "SLD") and o.ladder["level"] == 1
    assert o.exit == pytest.approx(E + 100) and usd(o) == pytest.approx(10.0)
    assert o.ladder["state"] == "cerrada_sl_dinamico" and audit_outcome(o) == []


def test_position_stays_open_at_each_step_no_fixed_tp():
    o = run(RISE)                                           # llega a +26 y sigue abierta
    assert o.status == "ABIERTA" and o.ladder["state"] == "protegida"
    assert o.ladder["level"] == 4 and o.ladder["nominal_usd"] == 25.0
    assert o.ladder["levels"] == [10.0, 15.0, 25.0]         # +20 no se «inventa»: saltó de 15 a 25
    assert o.ladder["stop"] == pytest.approx(E + 250)


def test_3_4_10_jump_crosses_several_steps_then_closes_at_last_confirmed():
    o = run(RISE + [(E + 300, E + 310, E + 240, E + 245)])
    assert o.reason == "SLD" and o.exit == pytest.approx(E + 250)
    assert usd(o) == pytest.approx(25.0) and o.ladder["max_float_usd"] == pytest.approx(26.0)


def test_4_climb_through_20_25_30_and_beyond_without_closing():
    bars = [(E, E + 100, E - 10, E + 100)]
    for k in range(1, 10):                       # cada vela +50 USDT de precio = +5 USDT netos
        top = E + 100 + 50 * k
        bars.append((top - 40, top, top - 45, top - 5))
    o = run(bars)
    assert o.status == "ABIERTA" and o.ladder["level"] == 10          # +55 → protege +55
    assert o.ladder["levels"][:5] == [10.0, 15.0, 20.0, 25.0, 30.0]
    assert o.ladder["levels"] == [10.0 + 5 * n for n in range(10)] and o.exit is None
    assert audit_outcome(o) == []


def test_5_pullback_without_touching_stop_stays_open():
    o = run(RISE + [(E + 255, E + 258, E + 251, E + 252)])
    assert o.status == "ABIERTA" and o.ladder["stop"] == pytest.approx(E + 250)


def test_7_profit_keeps_growing_no_cap():
    bars = [(E + 100 * k + 20, E + 100 * k + 40, E + 100 * k + 10, E + 100 * k + 35)
            for k in range(400)]
    o = run(bars)
    assert o.status == "ABIERTA" and o.ladder["level"] > 100 and o.exit is None


def test_8_9_short_mirrors_long():
    losing = [(E, E + 50, E - 10, E + 20), (E + 20, E + 30, E - 600, E - 550)]
    for bars in (RISE + [(E + 300, E + 310, E + 240, E + 245)], losing):
        lg, sh = run(bars, 1), run(bars, -1)
        assert (lg.status, lg.reason) == (sh.status, sh.reason)
        assert lg.ladder["levels"] == sh.ladder["levels"]
        assert usd(lg) == pytest.approx(usd(sh)) and sh.exit == pytest.approx(2 * E - lg.exit)
        assert audit_outcome(sh) == []


def test_short_protection_moves_down():
    o = run(RISE, -1)
    hist = [h["stop"] for h in o.ladder["stop_history"]]
    assert hist == sorted(hist, reverse=True) and hist[0] == pytest.approx(E - 100)
    assert o.ladder["stop"] == pytest.approx(E - 250)


def test_11_costs_and_slippage_realized_close_to_nominal():
    ep = ExecParams()
    bars = [(E, E + 300, E - 10, E + 290), (E + 400, E + 410, E + 100, E + 150)]
    o = run(bars, ep=ep)
    assert o.reason == "SLD" and o.ladder["level"] >= 1
    nom = o.ladder["nominal_usd"]
    paid = usd(o)                                    # neto en USDT, tras todos los costos
    assert nom - 0.5 < paid <= nom + 2.0     # la reserva deja el realizado ≥ nominal
    assert o.ladder["protected_est_usd"] >= nom - 0.05
    assert o.exit > o.fill + 100          # la salida (bruta) queda por encima de la entrada


def test_12_long_open_position_never_closes_by_time():
    bars = [(E, E + 20, E - 20, E)] + [(E, E + 20, E - 20, E)] * 3000    # ≈ 31 días
    o = run(bars, hold_h=0.01)                   # un `hold` ínfimo en la idea no cierra nada
    assert o.status == "ABIERTA" and o.reason == "" and o.ladder["elapsed_ms"] > 30 * 86_400_000
    assert audit_outcome(o) == []


def test_13_restart_recomputes_identical_state():
    full = run(RISE + [(E + 260, E + 270, E + 255, E + 262)])
    for n in range(1, len(RISE) + 2):
        part = run((RISE + [(E + 260, E + 270, E + 255, E + 262)])[:n])
        assert part.ladder["stop_history"] == full.ladder["stop_history"][:len(
            part.ladder["stop_history"])]           # la misma historia (sin anticipación)
        assert run((RISE + [(E + 260, E + 270, E + 255, E + 262)])[:n]) == part   # y repetible


def test_14_data_failure_leaves_open_with_incident():
    nan = math.nan
    o = run(RISE[:2] + [(nan, nan, nan, nan), (E, E, E - 900, E - 900)])
    assert o.status == "ABIERTA" and o.ladder["state"] == "incidencia"
    assert "sin datos válidos" in o.ladder["incident"] and o.exit is None
    assert o.ladder["level"] == 2                 # el nivel ya ganado no se pierde ni se «cierra»


def test_14b_stale_data_does_not_invent_a_close():
    o = run(RISE[:2])
    assert o.status == "ABIERTA" and o.ladder["last_bar_t"] == T0 + 2 * M15


def test_15_price_crosses_stop_between_updates():
    gap = run(RISE[:2] + [(E + 40, E + 45, E + 10, E + 20)])        # abre bajo el SL (hueco)
    assert gap.reason == "SLD" and gap.exit == pytest.approx(E + 40)
    assert usd(gap) < 15.0 and usd(gap) == pytest.approx(4.0)       # peor que el nominal
    assert audit_outcome(gap) == []


def test_conservative_stop_before_new_high_in_same_bar():
    o = run([(E, E + 100, E - 10, E + 90), (E + 150, E + 900, E + 90, E + 800)])
    assert o.reason == "SLD" and o.ladder["level"] == 1 and usd(o) == pytest.approx(10.0)


def test_16_protection_cannot_be_reduced_fuzz():
    rng = random.Random(7)
    for case in range(120):
        side = 1 if case % 2 == 0 else -1
        px, bars = E, []
        for _ in range(rng.randint(5, 80)):
            o_ = px
            c = px + rng.gauss(10, 90)
            hi, lo = max(o_, c) + abs(rng.gauss(0, 40)), min(o_, c) - abs(rng.gauss(0, 40))
            bars.append((o_, hi, lo, c))
            px = c
        o = run(bars, side, ep=ExecParams())
        assert audit_outcome(o) == [], (case, o.ladder)
        assert o.reason in ("", "SL", "SLD")


def test_16b_audit_flags_tampered_protection():
    o = run(RISE)
    bad = replace(o, ladder={**o.ladder, "stop_history": list(reversed(o.ladder["stop_history"]))})
    assert audit_outcome(bad)
    be = replace(o, ladder={**o.ladder, "stop_history": [
        {**o.ladder["stop_history"][0], "stop": E}] + o.ladder["stop_history"][1:]})
    assert any("break-even" in v for v in audit_outcome(be))


def test_17_18_forbidden_closes_are_violations_not_results():
    for r in ("TIEMPO", "TP", "BE", "NIVEL", "AGENTE", "MANUAL"):
        assert check_close_request(r)
    assert check_close_request("SL") is None and check_close_request("SLD") is None
    closed = run(RISE + [(E + 300, E + 310, E + 240, E + 245)])
    forged = replace(closed, reason="TIEMPO")
    assert any("tiempo" in v for v in audit_outcome(forged))
    assert any("Take Profit" in v for v in audit_outcome(replace(closed, reason="TP")))


def test_agent_view_cannot_change_the_outcome():
    a = run(RISE + [(E + 300, E + 310, E + 240, E + 245)], conf=0.9, syn_bias=0.9)
    b = run(RISE + [(E + 300, E + 310, E + 240, E + 245)], conf=0.1, syn_bias=-0.9, hold_h=0.0001)
    assert (a.exit, a.reason, a.ladder["stop_history"]) == (b.exit, b.reason,
                                                            b.ladder["stop_history"])


def test_limit_entry_and_no_lookahead_on_fill_bar():
    i = idea(kind="limit", entry=E - 50, sl=E - 550, tp=E + 1500, fill_h=2)
    bars = [(E, E + 500, E - 60, E - 40), (E - 40, E - 30, E - 45, E - 35)]   # llena en vela 0
    o = simulate_ladder(i, path_of(bars), ZERO, LP, QTY, spec=SPEC)
    assert o.fill == E - 50 and o.fill_t == T0 and o.status == "ABIERTA"
    assert o.ladder["level"] == 0                       # el avance de la vela de llenado no cuenta


def test_params_forbid_fixed_tp_time_exit_and_real_money():
    for k in ("fixed_take_profit", "time_exit", "real_money"):
        with pytest.raises(ValueError):
            LadderParams(**{k: True})


def test_slippage_reserve_uses_widest_recent_bar():
    """La reserva toma el mayor deslizamiento de las últimas velas: el SL queda más alto (largo)."""
    bars = [(E, E + 50, E - 500, E + 20), (E + 20, E + 400, E + 10, E + 390)]
    ep = ExecParams()
    i = idea(entry=E, sl=E - 900, tp=E + 1500)
    wide = simulate_ladder(i, path_of(bars), ep, LP, QTY, spec=SPEC)
    short = simulate_ladder(i, path_of(bars), ep, LadderParams(slip_lookback=1), QTY, spec=SPEC)
    assert wide.ladder["level"] >= 1 and short.ladder["level"] >= 1
    assert (wide.ladder["stop"] > short.ladder["stop"]
            or wide.ladder["level"] < short.ladder["level"])


def test_funding_reserve_puts_the_stop_above_the_nominal_level():
    bars = [(E, E + 300, E - 10, E + 290), (E + 290, E + 295, E + 280, E + 285)]
    ep = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0005)
    i = idea(entry=E, sl=E - 500, tp=E + 1500)
    a = simulate_ladder(i, path_of(bars), ep, LP, QTY, spec=SPEC)
    b = simulate_ladder(i, path_of(bars), ep, LadderParams(funding_reserve=0), QTY, spec=SPEC)
    assert (a.ladder["stop"] - E) * QTY > a.ladder["nominal_usd"] + 0.5   # colchón de funding
    assert (b.ladder["stop"] - E) * QTY == pytest.approx(b.ladder["nominal_usd"], abs=0.1)


# --- velas de 1 min en las velas ambiguas -------------------------------------------------
M1 = 60_000


def walk(points: list[float], t0: int) -> list:
    """15 velas de 1 min que recorren `points` en línea recta (reparto equitativo de minutos)."""
    segs = len(points) - 1
    out, px = [], points[0]
    for m in range(15):
        target = points[1 + min(segs - 1, m * segs // 15)]
        nxt = px + (target - px) / max(1, (m * segs // 15 + 1) * 15 // segs - m)
        out.append(bar(t0 + m * M1, px, max(px, nxt), min(px, nxt), nxt))
        px = nxt
    return out


def fine_of(walks: list[list[float]]) -> Path:
    cs = []
    for k, pts in enumerate(walks):
        cs += walk(pts, T0 + k * M15)
    return Path(cs, (), M1)


AMB_BARS = [(E, E + 125, E - 10, E + 125), (E + 125, E + 160, E + 90, E + 90)]
AMB_BARS_UP = [(E, E + 125, E - 10, E + 125), (E + 125, E + 160, E + 90, E + 160)]


def run_fine(bars, walks, fine=True):
    i = idea(entry=E, sl=E - 500, tp=E + 1500)
    return simulate_ladder(i, path_of(bars), ZERO, LP, QTY,
                           fine_of(walks) if fine else None, spec=SPEC)


def test_fine_resolves_rise_then_fall_better_than_conservative():
    walks = [[E, E - 10, E + 125, E + 125], [E + 125, E + 160, E + 90]]
    cons = run_fine(AMB_BARS, walks, fine=False)
    fine = run_fine(AMB_BARS, walks)
    assert cons.reason == "SLD" and usd(cons) == pytest.approx(10.0)       # regla conservadora
    assert fine.reason == "SLD" and fine.ladder["level"] == 2              # sube a +15 y cierra ahí
    assert fine.exit == pytest.approx(E + 150) and usd(fine) == pytest.approx(15.0)
    assert fine.ladder["fine_resolved_bars"] >= 1 and audit_outcome(fine) == []


def test_fine_resolves_fall_then_rise_same_as_conservative():
    walks = [[E, E - 10, E + 125, E + 125], [E + 125, E + 90, E + 160]]
    cons = run_fine(AMB_BARS_UP, walks, fine=False)
    fine = run_fine(AMB_BARS_UP, walks)
    assert fine.reason == "SLD" and fine.ladder["level"] == 1 and usd(fine) == pytest.approx(10.0)
    assert fine.exit == cons.exit            # cae primero: toca el SL antes de subirlo


def test_fine_missing_or_incomplete_falls_back_to_conservative():
    walks = [[E, E - 10, E + 125, E + 125], [E + 125, E + 160, E + 90]]
    incomplete = fine_of(walks[:1])                      # sin velas finas para la 2.ª vela
    i = idea(entry=E, sl=E - 500, tp=E + 1500)
    got = simulate_ladder(i, path_of(AMB_BARS), ZERO, LP, QTY, incomplete, spec=SPEC)
    assert usd(got) == pytest.approx(10.0) and got.ladder["fine_resolved_bars"] == 1


def test_fine_never_breaks_the_rules_fuzz():
    rng = random.Random(11)
    for case in range(60):
        side = 1 if case % 2 == 0 else -1
        px, bars, walks = E, [], []
        for _ in range(rng.randint(4, 40)):
            pts = [px] + [px + rng.gauss(0, 120) for _ in range(rng.randint(2, 5))]
            w = walk(pts, 0)
            bars.append((pts[0], max(c.h for c in w), min(c.l for c in w), w[-1].c))
            walks.append(pts)
            px = w[-1].c
        i = idea(side=side, entry=E, sl=E - side * 500, tp=E + side * 1500)
        p = path_of(bars, mirror=side < 0)
        fine = Path([bar(T0 + k * M15 + m * M1, *(
            (2 * E - c.o, 2 * E - c.l, 2 * E - c.h, 2 * E - c.c) if side < 0
            else (c.o, c.h, c.l, c.c))) for k, pts in enumerate(walks)
            for m, c in enumerate(walk(pts, 0))], (), M1)
        o = simulate_ladder(i, p, ExecParams(), LP, QTY, fine, spec=SPEC)
        assert audit_outcome(o) == [], (case, o.ladder)
