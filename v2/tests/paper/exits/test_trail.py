"""T132 — las propiedades de §5.2 que toda salida con arrastre tiene que cumplir.

Son las que impiden que una política «gane» por un defecto del motor: trinquete, piso de ruido,
sin anticipación, huecos a la apertura, determinismo bit a bit y E[R] ≈ 0 en paseo aleatorio sin
costos con cientos de semillas (la aceptación de T132).
"""

from __future__ import annotations

from dataclasses import fields

import numpy as np
import pytest

from eim.paper.engine import Path
from eim.paper.exits import features
from eim.paper.exits.rules import Chandelier, FixedStop, Structure
from eim.paper.exits.trail import TrailLimits, round_against, simulate_trail
from tests.paper.exits.helpers import COSTED, SPEC, ZERO, coherent_path, walk_path
from tests.paper.helpers import T0, bar, flat, idea

QTY = 0.01
M15 = 900_000


def path_of(rows) -> Path:
    return Path([bar(T0 + i * M15, *r) for i, r in enumerate(rows)])


def sig_of(path: Path, value: float) -> np.ndarray:
    """σ en precio constante, para aislar la mecánica del estimador."""
    return np.full(len(path.t), value)


def chand(path: Path, k: float = 2.0, s: float = 100.0, activate: float = 0.0) -> Chandelier:
    return Chandelier(k, sig_of(path, s), activate)


# --- trinquete y piso ----------------------------------------------------------------------
def test_the_stop_never_loosens_even_if_the_rule_proposes_worse():
    """Una regla que propone un stop peor cada vela no puede bajar el vigente."""
    rows = [(100.0, 101.0, 99.5, 100.5)] * 3 + [(100.5, 108.0, 100.0, 107.0)]
    rows += [(107.0, 107.5, 100.0, 100.5)] * 4
    p = path_of(rows)
    i = idea(entry=100.0, sl=98.0, tp=120.0, t=int(p.t[0]))

    class Sinking:
        id = "bajista"

        def __init__(self):
            self.n = 0

        def phase_at(self, st, j, extreme):
            return "arrastre"

        def stop_at(self, st, j, extreme):
            self.n += 1
            return 99.0 + max(0, 4 - self.n)      # primero sube y luego propone cada vez peor

    o = simulate_trail(i, p, ZERO, Sinking(), QTY, spec=SPEC)
    stops = [i.sl] + [h["stop"] for h in o.ladder["stop_history"]]
    assert all(b >= a for a, b in zip(stops, stops[1:], strict=False))


def test_no_stop_lands_closer_than_the_noise_floor():
    p = walk_path(200, seed=5)
    px = float(p.c[0])
    i = idea(entry=px, sl=px * 0.99, tp=px * 1.1, t=int(p.t[1]))
    s = px * 0.004
    rule = Chandelier(0.1, sig_of(p, s))          # k diminuto: querría pegarse al precio
    o = simulate_trail(i, p, ZERO, rule, QTY, spec=SPEC, sigma_abs=sig_of(p, s),
                       limits=TrailLimits(floor_n=3.0))
    for h in o.ladder["stop_history"]:
        assert h["extreme"] - h["stop"] >= 3.0 * s - 1e-6


def test_without_sigma_the_floor_does_not_tighten():
    """Falta de datos no aprieta: sin σ el piso no se aplica y la política usa su candidato."""
    p = walk_path(120, seed=6)
    px = float(p.c[0])
    i = idea(entry=px, sl=px * 0.99, tp=px * 1.1, t=int(p.t[1]))
    nan_sig = np.full(len(p.t), np.nan)
    rule = Chandelier(2.0, sig_of(p, px * 0.003))
    o = simulate_trail(i, p, ZERO, rule, QTY, spec=SPEC, sigma_abs=nan_sig,
                       limits=TrailLimits(floor_n=99.0))
    assert o.ladder["stop_history"], "con σ ausente el piso no debe bloquear el arrastre"


def test_a_rule_without_sigma_proposes_nothing_and_the_initial_stop_rules():
    p = walk_path(120, seed=7)
    px = float(p.c[0])
    i = idea(entry=px, sl=px * 0.995, tp=px * 1.1, t=int(p.t[1]))
    o = simulate_trail(i, p, ZERO, Chandelier(2.0, np.full(len(p.t), np.nan)), QTY, spec=SPEC)
    assert o.ladder["stop_history"] == []
    assert o.ladder["stop"] == i.sl


# --- sin anticipación ----------------------------------------------------------------------
def test_the_advance_of_a_bar_only_moves_the_stop_from_the_next_one():
    """La vela que dispara el arrastre no puede cerrarse a ese stop nuevo (regla conservadora).

    La vela 1 sube a 110 y vuelve a 99,9: el candidato (109) queda por debajo de su mínimo, así
    que la vela es **ambigua**. Sin velas de 1 min no se sabe el orden, y la regla de `ladder.py`
    manda: durante la vela sigue el stop viejo y el nuevo solo rige desde la siguiente. Por eso el
    stop se anota al CERRAR su vela y el cierre llega en una vela posterior, nunca en la misma.
    """
    rows = [(100.0, 100.2, 99.8, 100.0), (100.0, 110.0, 99.9, 100.0), (100.0, 100.5, 90.0, 90.0)]
    p = path_of(rows)
    i = idea(entry=100.0, sl=98.0, tp=130.0, t=int(p.t[0]))
    o = simulate_trail(i, p, ZERO, chand(p, k=1.0, s=1.0), QTY, spec=SPEC)
    for h in o.ladder["stop_history"]:
        assert h["t"] == int(p.t[h["bar"]]) + p.step    # se confirma al cerrar su propia vela
    last = o.ladder["stop_history"][-1]
    assert last["stop"] == pytest.approx(109.0)
    assert o.exit_t > last["t"]                         # el cierre, en una vela posterior
    assert int(np.searchsorted(p.t, o.exit_t) - 1) > last["bar"]


def test_the_result_does_not_change_if_later_bars_are_rewritten():
    p = walk_path(300, seed=9)
    px = float(p.c[0])
    i = idea(entry=px, sl=px * 0.99, tp=px * 1.05, t=int(p.t[1]))
    rule = chand(p, k=2.0, s=px * 0.004)
    base = simulate_trail(i, p, ZERO, rule, QTY, spec=SPEC)
    cut = int(np.searchsorted(p.t, base.exit_t))
    p2 = Path([bar(int(p.t[j]), float(p.o[j]), float(p.h[j]), float(p.l[j]), float(p.c[j]))
               if j <= cut else bar(int(p.t[j]), 1.0, 2.0, 0.5, 1.0) for j in range(len(p.t))])
    again = simulate_trail(i, p2, ZERO, chand(p2, k=2.0, s=px * 0.004), QTY, spec=SPEC)
    assert (again.exit_t, again.exit, again.reason) == (base.exit_t, base.exit, base.reason)


# --- huecos, determinismo y casos límite ---------------------------------------------------
def test_a_gap_beyond_the_stop_fills_at_the_open():
    rows = [(100.0, 100.2, 99.9, 100.0), (100.0, 106.0, 99.9, 105.0), (90.0, 91.0, 85.0, 86.0)]
    p = path_of(rows)
    i = idea(entry=100.0, sl=98.0, tp=130.0, t=int(p.t[0]))
    o = simulate_trail(i, p, ZERO, chand(p, k=1.0, s=1.0), QTY, spec=SPEC)
    assert o.exit == 90.0 and o.reason == "SLD"     # la apertura, no el stop


@pytest.mark.parametrize("ep", [ZERO, COSTED])
@pytest.mark.parametrize("side", [1, -1])
def test_a_policy_is_deterministic_bit_for_bit(ep, side):
    p = walk_path(250, seed=13)
    px = float(p.c[0])
    i = idea(side=side, entry=px, sl=px - side * px * 0.01, tp=px + side * px * 0.05,
             t=int(p.t[1]))
    rule = chand(p, k=2.5, s=px * 0.004)
    a, b = (simulate_trail(i, p, ep, rule, QTY, spec=SPEC) for _ in range(2))
    for f in fields(a):
        assert getattr(a, f.name) == getattr(b, f.name), f.name


def test_flat_prices_close_nothing():
    p = Path(flat(60, price=100.0, spread=0.0))
    i = idea(entry=100.0, sl=98.0, tp=104.0, t=int(p.t[1]))
    for rule in (chand(p, s=1.0), FixedStop(), Structure(None, None, None)):
        o = simulate_trail(i, p, ZERO, rule, 1.0, spec=SPEC)
        assert o.status == "ABIERTA", rule.id


def test_a_bar_without_valid_data_leaves_the_position_open_and_marked():
    rows = [(100.0, 101.0, 99.0, 100.0)] * 3
    p = path_of(rows)
    p.h[2] = np.nan
    i = idea(entry=100.0, sl=98.0, tp=110.0, t=int(p.t[0]))
    # Con `FixedStop` nada mueve el stop, así que la posición llega viva a la vela sin datos.
    o = simulate_trail(i, p, ZERO, FixedStop(), QTY, spec=SPEC)
    assert o.status == "ABIERTA" and o.ladder["incident"]
    assert o.exit_t is None, "una vela sin datos no puede inventar un cierre"


def test_the_tick_rounding_goes_against_the_operator():
    assert round_against(100.04, 1, 0.1) == pytest.approx(100.1)     # largo: hacia arriba
    assert round_against(100.06, -1, 0.1) == pytest.approx(100.0)    # corto: hacia abajo


# --- la propiedad de aceptación: paseo aleatorio sin costos ≈ 0 -----------------------------
PATHS = 300
BARS = 300


def _random_walk_expectancy(rule_of, ep, use_fine: bool = False,
                            seed0: int = 5000) -> np.ndarray:
    """R de cada operación sobre caminos **coherentes** (15 m agregado de 1 min).

    Dos cuidados que cambian el resultado:
    - El camino se agrega de velas de 1 min reales. Con mechas sorteadas aparte del recorrido, el
      extremo de la vela no corresponde a ningún camino y un arrastre que ancla en él sale sesgado
      (medido: −0,11 R con `walk_path`, 0,00 R con el camino coherente).
    - Se cuentan también las posiciones **vivas** al final con su R latente: con un arrastre, las
      que no han cerrado son justo las que corrieron a favor, y excluirlas tira ganadoras.
    """
    out = []
    for s in range(PATHS):
        p, fine = coherent_path(BARS, seed=seed0 + s)
        px = float(p.c[1])
        side = 1 if s % 2 == 0 else -1
        i = idea(side=side, entry=px, sl=px - side * px * 0.01,
                 tp=px + side * px * 0.02, t=int(p.t[1]) + p.step)
        o = simulate_trail(i, p, ep, rule_of(p, px), QTY, spec=SPEC,
                           fine=fine if use_fine else None)
        if o.status in ("CERRADA", "ABIERTA") and o.r is not None:
            out.append(o.r)
    return np.array(out, dtype=float)


@pytest.mark.parametrize("use_fine", [False, True])
@pytest.mark.parametrize("name,rule_of", [
    ("M2 k=1", lambda p, px: Chandelier(1.0, np.full(len(p.t), px * 0.004))),
    ("M2 k=2.5", lambda p, px: Chandelier(2.5, np.full(len(p.t), px * 0.004))),
    ("M3", lambda p, px: Structure(*features.swings(p.h, p.l, 5),
                                   np.full(len(p.t), px * 0.004))),
])
def test_on_a_random_walk_without_costs_the_expectancy_is_zero(name, rule_of, use_fine):
    """Propiedad 7 de §5.2 con cientos de semillas: sin costos y sin dependencia, E[R] ≈ 0.

    Se prueba con y sin velas de 1 min: la resolución de las velas ambiguas no puede crear
    esperanza donde no la hay, que es justo lo que el control de T131 vigila en el banco.
    """
    r = _random_walk_expectancy(rule_of, ZERO, use_fine)
    assert len(r) > 250, f"{name}: solo {len(r)} operaciones"
    half = 1.96 * float(r.std(ddof=1)) / np.sqrt(len(r))
    assert abs(float(r.mean())) <= half, f"{name}: E[R] {r.mean():+.4f} fuera de ±{half:.4f}"


def test_with_costs_the_random_walk_loses_about_the_costs():
    r = _random_walk_expectancy(lambda p, px: Chandelier(2.5, np.full(len(p.t), px * 0.004)),
                                COSTED)
    assert float(r.mean()) < 0                     # con costos solo puede perder


def test_a_stop_only_policy_can_only_close_at_its_stop():
    """`FixedStop` no tiene salida favorable: toda operación cerrada lo está en su SL inicial.

    No es un defecto, es su definición, y por eso no entra en la propiedad de E[R] ≈ 0: su
    esperanza **condicionada a haber cerrado** es −1 R por construcción.
    """
    closed = 0
    for s in range(40):
        p = walk_path(400, seed=900 + s)
        px = float(p.c[1])
        i = idea(entry=px, sl=px * 0.99, tp=px * 1.02, t=int(p.t[1]) + p.step)
        o = simulate_trail(i, p, ZERO, FixedStop(), QTY, spec=SPEC)
        if o.status == "CERRADA":
            closed += 1
            assert o.reason == "SL" and o.r == pytest.approx(-1.0, abs=1e-9)
            assert o.ladder["stop_history"] == []
    assert closed > 10
