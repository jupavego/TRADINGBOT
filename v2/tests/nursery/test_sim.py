"""Simulación de una operación de la cantera (T168): maker conservador, markout y funding."""

from __future__ import annotations

from eim.core import Candle
from eim.nursery import sim
from eim.nursery.sim import Order, funding_paid, funding_step, simulate
from eim.paper.engine import Path
from eim.paper.params import LADDER_BY_PROFILE, ExecParams
from tests.nursery.helpers import H1, M15, T0

EP = ExecParams()


def _path(rows: list[tuple[float, float, float, float]], funding=()) -> Path:
    cs = [Candle(t=T0 + k * M15, o=o, h=h, l=lo, c=c, v=1.0) for k, (o, h, lo, c) in
          enumerate(rows)]
    return Path(cs, funding, M15)


FLAT = [(100.0, 100.5, 99.5, 100.0)] * 12


def test_limit_that_only_touches_is_not_filled():
    rows = [(100.5, 101.0, 100.0, 100.6)] + [(100.6, 101.0, 100.2, 100.8)] * 8
    o = Order(side=1, t=T0, ref=100.0, sl=98.0, maker=True, fill_ms=4 * M15)
    tr = simulate(o, _path(rows), EP)
    assert tr.status == "NO_LLENADA" and tr.r == 0.0
    rows[1] = (100.6, 101.0, 99.99, 100.8)       # ahora sí lo atraviesa
    tr2 = simulate(o, _path(rows), EP)
    assert tr2.status in ("ABIERTA", "CERRADA") and tr2.fill == 100.0
    assert tr2.fee_in == EP.costs.maker_fee and tr2.slip == 0.0


def test_markout_is_recorded_after_fill():
    rows = [(100.5, 101.0, 99.0, 100.0)] + [(100.0, 100.5, 99.8, 100.4)] * 10
    o = Order(side=1, t=T0, ref=100.0, sl=97.0, maker=True, fill_ms=4 * M15)
    tr = simulate(o, _path(rows), EP)
    assert tr.fill_t == T0 and tr.markout_bps is not None
    assert round(tr.markout_bps, 6) == round((100.4 - 100.0) / 100.0 * 1e4, 6)


def test_funding_uses_the_symbol_frequency():
    every4h = [(T0 + k * 4 * H1, 0.0001) for k in range(1, 7)]
    p = _path(FLAT * 8, every4h)
    assert funding_step(p) == 4 * H1
    paid, assumed = funding_paid(p, 1, T0, T0 + 24 * H1, EP, 4 * H1)
    assert not assumed and abs(paid - 0.0006) < 1e-12
    # sin cobros guardados en el tramo, se supone la tasa escalada a la frecuencia real
    paid2, assumed2 = funding_paid(_path(FLAT), 1, T0, T0 + 8 * H1, EP, 4 * H1)
    assert assumed2 and abs(paid2 - 2 * EP.funding_8h_assumed / 2) < 1e-12


def test_stop_and_time_exit_and_costs():
    rows = [(100.0, 100.2, 99.9, 100.0)] * 3 + [(100.0, 100.1, 97.0, 97.5)] + FLAT
    tr = simulate(Order(side=1, t=T0, ref=100.0, sl=98.0), _path(rows), EP)
    assert tr.status == "CERRADA" and tr.reason == "SL" and tr.exit == 98.0
    assert tr.fee_in == EP.costs.taker_fee and tr.r < -1.0     # pierde 1 R más los costos
    tt = simulate(Order(side=1, t=T0, ref=100.0, sl=95.0, forced_t=T0 + 2 * M15),
                  _path(FLAT), EP)
    assert tt.reason == "TIEMPO" and tt.exit_t == T0 + 2 * M15


def test_twins_mirror_the_geometry_and_cap_the_exit():
    o = Order(side=1, t=T0, ref=100.0, sl=98.0, tp=105.0, forced_t=T0 + 8 * M15)
    tw = o.twin(-1, T0 + 4 * M15)
    assert tw.side == -1 and tw.sl == 102.0 and tw.tp == 95.0 and tw.forced_t == T0 + 4 * M15


def test_ladder_is_the_moderate_profile_without_brake_or_weight():
    lp = LADDER_BY_PROFILE[sim.PROFILE]
    assert (sim.PROTECT_FIRST, sim.PROTECT_STEP) == (lp.first_r, lp.step_r)
    rows = [(100.0, 100.1, 99.9, 100.0), (100.0, 101.2, 99.95, 101.0),
            (101.0, 101.1, 99.0, 99.2)] + FLAT
    tr = simulate(Order(side=1, t=T0, ref=100.0, sl=98.0, protect=True), _path(rows), EP)
    assert tr.reason == "SLD" and tr.exit > tr.fill    # el escalón protegió ganancia
