"""T109 — En los tres perfiles solo cierra el stop: casos A–G, I, J y K en el motor de la escalera.

Cada caso corre con los parámetros REALES de escalera del Conservador, el Moderado y el Agresivo
(umbrales en R, T108), en largo y en corto. Precios a escala BTC con `qty` = 0,1 BTC y el SL a
500 USDT de precio: el riesgo es 50 USDT y los escalones salen de `LadderParams.steps(50)`
(5 / 2,5 · 5 / 2,5 · 3,75 / 1,875 USDT). Los caminos se escriben en USDT de beneficio de la
operación (`u`): precio = entrada + lado · u / qty, así que el corto es el espejo del largo.

Casos (letras del encargo): A sin alcanzar el umbral (stop inicial intacto) · B activación sin
cierre · C avance de escalón · D retroceso sin tocar el stop · E retroceso hasta el stop · F costos
(objetivo estimado ≠ neto realizado) · G varios escalones en una actualización · I sin
información futura (vela ambigua) · J nadie más cierra · K duración prolongada sin cierre.
"""

from __future__ import annotations

import pytest

from eim.backtest.params import ZERO_COSTS
from eim.paper.engine import Outcome, Path
from eim.paper.ladder import LadderCosts, protect_price, simulate_ladder
from eim.paper.ladder_audit import audit_outcome
from eim.paper.params import PROFILES, ExecParams, spec_for
from tests.paper.helpers import M15, T0, bar, fine_of, idea, walk

E, QTY, D = 70_000.0, 0.1, 500.0
ZERO = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
SPEC = spec_for("BTCUSDT")
P = {p.id: p for p in PROFILES}
IDS = ("conservador", "moderado", "agresivo")
CASES = [(pid, side) for pid in IDS for side in (1, -1)]
FREE = LadderCosts(0.0, 0.0, 0.0, 0.0)


def steps(pid: str) -> tuple[float, float]:
    return P[pid].ladder.steps(QTY * D)


def price(u: float, side: int) -> float:
    return E + side * u / QTY


def path_usd(rows: list[tuple[float, float, float, float]], side: int) -> Path:
    """Velas de 15 m desde T0 escritas en USDT de beneficio (o, mejor, peor, c)."""
    out = []
    for k, (o, best, worst, c) in enumerate(rows):
        hi, lo = (best, worst) if side > 0 else (worst, best)
        out.append(bar(T0 + k * M15, price(o, side), price(hi, side), price(lo, side),
                       price(c, side)))
    return Path(out)


def run(pid: str, side: int, rows, ep: ExecParams = ZERO, fine: Path | None = None,
        **kw) -> Outcome:
    i = idea(side=side, entry=E, sl=E - side * D, tp=E + side * 1500, **kw)
    return simulate_ladder(i, path_usd(rows, side), ep, P[pid].ladder, QTY, fine, spec=SPEC)


def usd(o: Outcome) -> float:
    return o.net * o.fill * QTY


def stop_at(nominal: float, side: int) -> float:
    """Precio del SL que protege `nominal` USDT netos (sin costos), redondeado al tick."""
    return protect_price(side, QTY, E, nominal, 0.0, FREE, SPEC.tick)


def climb(f: float, st: float) -> list[tuple[float, float, float, float]]:
    """Activa (escalón 1), sube al 2 y al 3 sin tocar nunca el stop vigente."""
    return [(0, f + 0.2 * st, -1, f + 0.1 * st),
            (f + 0.1 * st, f + 1.2 * st, f + 0.05 * st, f + 1.1 * st),
            (f + 1.1 * st, f + 2.3 * st, f + 1.05 * st, f + 2.2 * st)]


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_A_below_the_threshold_the_initial_stop_is_untouched(pid, side):
    f, _ = steps(pid)
    o = run(pid, side, [(0, 0.8 * f, -10, 0.5 * f), (0.5 * f, 0.7 * f, -20, 0.2 * f)])
    assert o.status == "ABIERTA" and o.ladder["level"] == 0 and o.ladder["stop_history"] == []
    assert o.ladder["stop"] == E - side * D and o.ladder["state"] == "inicial"
    lost = run(pid, side, [(0, 0.8 * f, -10, 0.5 * f), (0, 0.1 * f, -60, -55)])
    assert (lost.reason, lost.exit) == ("SL", E - side * D) and usd(lost) == pytest.approx(-50)
    assert lost.ladder["state"] == "cerrada_sl_inicial" and audit_outcome(lost) == []


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_B_activation_does_not_close(pid, side):
    f, st = steps(pid)
    o = run(pid, side, [(0, f + 0.2 * st, -1, f + 0.1 * st),
                        (f + 0.1 * st, f + 0.15 * st, f + 0.05 * st, f + 0.1 * st)])
    assert o.status == "ABIERTA" and o.ladder["state"] == "protegida" and o.ladder["level"] == 1
    assert o.ladder["stop"] == pytest.approx(stop_at(f, side)) and o.exit is None
    assert o.ladder["stop_source"] == "escalon" and audit_outcome(o) == []


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_C_each_step_raises_the_stop_and_nothing_closes(pid, side):
    f, st = steps(pid)
    o = run(pid, side, climb(f, st))
    assert o.status == "ABIERTA" and o.ladder["level"] == 3
    assert o.ladder["levels"] == pytest.approx([f, f + st, f + 2 * st])
    stops = [h["stop"] for h in o.ladder["stop_history"]]
    assert stops == [pytest.approx(stop_at(f + k * st, side)) for k in range(3)]
    assert all((b - a) * side > 0 for a, b in zip(stops, stops[1:], strict=False))


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_D_pullback_without_touching_the_stop_keeps_level_and_stop(pid, side):
    f, st = steps(pid)
    o = run(pid, side, climb(f, st) + [(f + 2.2 * st, f + 2.25 * st, f + 2.05 * st,
                                        f + 2.1 * st)])
    assert o.status == "ABIERTA" and o.ladder["level"] == 3
    assert o.ladder["stop"] == pytest.approx(stop_at(f + 2 * st, side))
    assert o.ladder["max_float_usd"] == pytest.approx(f + 2.3 * st)   # el máximo no se olvida


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_E_pullback_to_the_stop_closes_as_dynamic_stop(pid, side):
    f, st = steps(pid)
    o = run(pid, side, climb(f, st) + [(f + 2.2 * st, f + 2.25 * st, f + st, f + 1.2 * st)])
    assert (o.status, o.reason) == ("CERRADA", "SLD") and o.ladder["level"] == 3
    assert o.exit == pytest.approx(stop_at(f + 2 * st, side))
    assert usd(o) == pytest.approx(f + 2 * st, abs=0.011)          # un tick de 0,1 × 0,1 BTC
    assert o.ladder["state"] == "cerrada_sl_dinamico" and audit_outcome(o) == []


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_F_estimated_target_is_not_the_realized_net(pid, side):
    """Con costos reales: el objetivo de la idea (150 USDT brutos) solo fue una estimación; lo
    realizado es el neto del stop dinámico, tras comisiones, deslizamiento y funding."""
    o = run(pid, side, [(0, 30, -1, 25), (29, 29.5, 5, 6)], ep=ExecParams())
    nom = o.ladder["nominal_usd"]
    assert o.reason == "SLD" and o.ladder["level"] >= 1 and o.exit != o.idea.tp
    gross = (o.exit - o.fill) * side * QTY
    assert usd(o) < gross                                    # los costos están dentro del neto
    assert abs(usd(o) - nom) < 2.0 and usd(o) < abs(o.idea.tp - E) * QTY
    assert o.ladder["protected_est_usd"] >= nom - 0.05 and audit_outcome(o) == []


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_G_several_steps_in_one_update_apply_the_last_confirmed(pid, side):
    f, st = steps(pid)
    o = run(pid, side, [(0, f + 3.4 * st, -1, f + 3.3 * st),
                        (f + 3.3 * st, f + 3.35 * st, f + 3.1 * st, f + 3.2 * st)])
    assert o.status == "ABIERTA" and o.ladder["level"] == 4
    (h,) = o.ladder["stop_history"]                          # un solo movimiento, sin inventar
    assert h["level"] == 4 and o.ladder["levels"] == pytest.approx([f + 3 * st])
    assert o.ladder["stop"] == pytest.approx(stop_at(f + 3 * st, side))


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_I_no_future_information_inside_a_bar(pid, side):
    """La vela que sube el escalón y vuelve al stop anterior cierra en el stop VIGENTE al abrir;
    el avance de una vela solo sube el stop desde la siguiente; con velas de 1 min se usa el
    orden real (sube y baja → stop nuevo; baja y sube → el mismo cierre que la regla)."""
    f, st = steps(pid)
    r0 = (0, f + 0.2 * st, -1, f + 0.1 * st)
    amb = run(pid, side, [r0, (f + 0.1 * st, f + 2.5 * st, f - 0.2 * st, f + 0.5 * st)])
    assert (amb.reason, amb.ladder["level"]) == ("SLD", 1)
    assert amb.exit == pytest.approx(stop_at(f, side))
    later = run(pid, side, [r0, (f + 0.1 * st, f + 2.5 * st, f + 0.05 * st, f + 2.4 * st),
                            (f + 2.4 * st, f + 2.45 * st, f + 1.5 * st, f + 1.6 * st)])
    assert later.reason == "SLD" and later.exit == pytest.approx(stop_at(f + 2 * st, side))
    for pts, level in (([f + 0.1 * st, f + 2.5 * st, f - 0.2 * st], 3),
                       ([f + 0.1 * st, f - 0.2 * st, f + 2.5 * st], 1)):
        walks = [[price(u, side) for u in w] for w in ([0, -1, f + 0.2 * st, f + 0.1 * st], pts)]
        cs = [walk(w, T0 + k * M15) for k, w in enumerate(walks)]
        path = Path([bar(c[0].t, c[0].o, max(x.h for x in c), min(x.l for x in c), c[-1].c)
                     for c in cs])
        i = idea(side=side, entry=E, sl=E - side * D, tp=E + side * 1500)
        o = simulate_ladder(i, path, ZERO, P[pid].ladder, QTY, fine_of(walks), spec=SPEC)
        assert o.reason == "SLD" and o.ladder["level"] == level and audit_outcome(o) == []
    full = climb(f, st) + [(f + 2.2 * st, f + 2.25 * st, f + st, f + 1.2 * st)]
    for n in range(1, len(full)):                            # el pasado no cambia con el futuro
        part = run(pid, side, full[:n]).ladder["stop_history"]
        assert part == run(pid, side, full).ladder["stop_history"][:len(part)]


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_J_nobody_else_closes(pid, side):
    """Ni la opinión de los agentes, ni la confianza, ni el horizonte de la idea cambian la
    salida: solo el stop. (Los cierres fabricados en el libro: `test_ladder_book.py`.)"""
    f, st = steps(pid)
    rows = climb(f, st) + [(f + 2.2 * st, f + 2.25 * st, f + st, f + 1.2 * st)]
    a = run(pid, side, rows, conf=0.9, syn_bias=0.9 * side)
    b = run(pid, side, rows, conf=0.05, syn_bias=-0.9 * side, hold_h=0.0001)
    assert (a.exit, a.reason, a.ladder["stop_history"]) == (b.exit, b.reason,
                                                            b.ladder["stop_history"])
    assert a.reason in ("SL", "SLD")


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_K_long_duration_is_recorded_never_closes(pid, side):
    f, st = steps(pid)
    rows = [(0, f + 0.2 * st, -1, f + 0.1 * st)]
    rows += [(f + 0.3 * st, f + 0.6 * st, f + 0.1 * st, f + 0.3 * st)] * 3000   # ≈ 31 días
    o = run(pid, side, rows, hold_h=0.01)                    # un horizonte ínfimo no cierra nada
    assert o.status == "ABIERTA" and o.reason == "" and o.ladder["level"] == 1
    assert o.ladder["elapsed_ms"] > 30 * 86_400_000 and audit_outcome(o) == []
