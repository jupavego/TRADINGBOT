"""T135 — El suelo del diario T110 en el motor de arrastre: mismas reglas que la escalera.

Lo guardado manda si protege más y nunca baja; si no deja reconstruir la operación, queda
«inconsistente», abierta y sin cierre inventado. Sin `guard` el motor es exactamente el de T134.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from eim.backtest.params import ZERO_COSTS
from eim.paper.engine import Path
from eim.paper.exits.rules import Chandelier, FixedStop
from eim.paper.exits.trail import TrailLimits, simulate_trail
from eim.paper.ladder_floor import Floor, Guard
from eim.paper.params import ExecParams, spec_for
from tests.paper.helpers import M15, T0, bar, idea

E = 70_000.0
EP = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
SPEC = spec_for("BTCUSDT")
QTY = 0.01
SIDE = 1
ROWS = ([(E, E + 50, E - 20, E + 30)] * 2
        + [(E + 30, E + 1000, E + 20, E + 990)]
        + [(E + 990, E + 1000, E + 900, E + 950)] * 4)
SL = E - 1400


def path(rows=ROWS) -> Path:
    return Path([bar(T0 + k * M15, *r) for k, r in enumerate(rows)])


def btc():
    return replace(idea(side=SIDE, entry=E, sl=SL, tp=E + 3000, t=T0), symbol="BTCUSDT", htf=1)


def rule(n: int, k=3.0, sigma=100.0):
    return Chandelier(k, np.full(n, sigma), id="M2@x")


def run(guard=None, rows=ROWS, r=None, limits=None, **kw):
    return simulate_trail(btc(), path(rows), EP, r or rule(len(rows)), QTY, spec=SPEC,
                          sigma_abs=np.full(len(rows), 100.0), limits=limits or TrailLimits(),
                          guard=guard, **kw)


def floor(stop, t=T0 + 3 * M15, level=1, side=SIDE, fill=None, qty=QTY, seq=2):
    # la entrada a mercado llena a la apertura de la primera vela, E con costos cero
    return Floor(seq, t, side, fill if fill is not None else E, qty, stop, level, None, None)


def test_without_guard_nothing_changes():
    a, b = run(), run(guard=None)
    assert a == b
    assert a.ladder["recovered"] is None and a.ladder["inconsistent"] is None


def test_better_saved_stop_is_adopted_from_its_instant():
    o = run(Guard(floor(E + 800, t=T0 + 4 * M15)))
    assert o.ladder["recovered"]["to_stop"] == E + 800
    assert o.ladder["stop"] >= E + 800 and o.status == "ABIERTA"
    assert any(h["source"] == "recuperado" for h in o.ladder["stop_history"])


def test_saved_stop_never_lowers_what_the_recalculation_protects():
    o = run(Guard(floor(E - 1000, t=T0 + 3 * M15)))
    assert o.ladder["recovered"] is None
    assert o.ladder["stop"] > E - 1000       # el arrastre ya estaba por encima de lo guardado


def test_close_after_the_floor_counts_as_dynamic_stop():
    rows = [*ROWS, (E + 950, E + 960, E + 100, E + 120)]
    fixed = FixedStop(id="M2@x")
    o = simulate_trail(btc(), path(rows), EP, fixed, QTY, spec=SPEC,
                       sigma_abs=np.full(len(rows), 100.0),
                       guard=Guard(floor(E + 800, t=T0 + 4 * M15)))
    assert o.status == "CERRADA" and o.reason == "SLD" and o.exit == E + 800
    assert o.ladder["moved"] is True


@pytest.mark.parametrize(("kw", "text"), [
    ({"side": -1}, "lado"), ({"fill": E + 500}, "entrada"), ({"qty": QTY * 2}, "cantidad")])
def test_snapshot_that_does_not_match_leaves_it_open_and_held(kw, text):
    rows = [*ROWS, (E + 950, E + 960, E - 2000, E - 1900)]
    o = run(Guard(floor(E + 800, t=T0 + 4 * M15, **kw)), rows=rows)
    assert o.status == "ABIERTA"
    assert text in o.ladder["inconsistent"] and o.ladder["state"] == "inconsistente"


def test_explicit_hold_never_invents_a_close():
    rows = [*ROWS, (E + 950, E + 960, E - 2000, E - 1900)]
    o = run(Guard(None, "falta la instantánea"), rows=rows)
    assert o.status == "ABIERTA" and o.reason == ""
    assert o.ladder["inconsistent"] == "falta la instantánea"


def test_recalculation_that_closes_before_the_saved_instant_is_held():
    rows = [(E, E + 50, E - 2000, E - 1900), *ROWS]        # toca el SL en la primera vela
    o = run(Guard(floor(E + 800, t=T0 + 5 * M15)), rows=rows)
    assert o.status == "ABIERTA"
    assert "antes del estado guardado" in o.ladder["inconsistent"]


def test_candles_that_do_not_reach_the_saved_instant_are_held():
    o = run(Guard(floor(E + 800, t=T0 + 500 * M15)))
    assert o.status == "ABIERTA"
    assert "terminan" in o.ladder["inconsistent"]


def test_time_barrier_respects_the_hold():
    o = run(Guard(None, "congelada"), limits=TrailLimits(time_bars=1))
    assert o.status == "ABIERTA" and o.ladder["inconsistent"] == "congelada"


def test_level_counts_the_moves_and_history_carries_it():
    o = run()
    assert o.ladder["level"] == len(o.ladder["stop_history"]) >= 1
    assert [h["level"] for h in o.ladder["stop_history"]] == list(
        range(1, o.ladder["level"] + 1))
    assert o.ladder["stop_source"] == "M2@x"
