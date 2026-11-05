"""T136 (1): el riesgo presupuestado incluye el costo de ida y vuelta."""

from __future__ import annotations

import pytest

from eim.paper import risk_budget as rb
from eim.paper.params import PROFILES


def test_cost_r_is_the_same_number_the_veto_used():
    """La definición centralizada da, al dígito, lo que calculaba `vetoes.py`."""
    entry, sl, frac = 100_000.0, 99_000.0, 0.0016
    assert rb.cost_r(entry, sl, frac) == frac / ((abs(entry - sl) / entry) or 1e-9)
    assert rb.cost_r(entry, sl, frac) == pytest.approx(0.16, abs=1e-12)


def test_flat_geometry_does_not_divide_by_zero():
    big = rb.cost_r(100.0, 100.0, 0.0016)
    assert big > 1e5                                   # veta por costo, no revienta
    assert rb.cost_r(0.0, 10.0, 0.0016) > 1e5
    assert rb.qty_for_risk(100.0, 100.0, 100.0, 0.0016) == 0.0
    assert rb.budget_distance(100.0, 100.0, 0.0016) == 0.0


def test_loss_at_stop_is_exactly_the_budget_when_costs_are_included():
    """Lo que de verdad se pierde al saltar el SL inicial: con costos incluidos, el riesgo."""
    risk, entry, sl, frac = 100.0, 50_000.0, 49_500.0, 0.0016
    assert rb.loss_at_stop(risk, entry, sl, frac, True) == pytest.approx(risk)
    hoy = rb.loss_at_stop(risk, entry, sl, frac, False)
    assert hoy == pytest.approx(risk * (1 + rb.cost_r(entry, sl, frac)))
    assert hoy > risk                                   # hoy se arriesga de más


def test_including_costs_only_reduces_the_quantity():
    risk, entry, sl, frac = 100.0, 50_000.0, 49_500.0, 0.0016
    con = rb.qty_for_risk(risk, entry, sl, frac, True)
    sin = rb.qty_for_risk(risk, entry, sl, frac, False)
    assert 0 < con < sin
    assert con / sin == pytest.approx(1 / (1 + rb.cost_r(entry, sl, frac)))


def test_off_by_default_in_every_profile():
    """Encenderlo cambia el tamaño de una corrida en marcha: es decisión ◆ del usuario."""
    assert all(not p.risk_includes_costs for p in PROFILES)


def test_sizing_with_costs_off_is_bit_for_bit_what_the_policy_did():
    entry, sl, risk = 50_000.0, 49_500.0, 100.0
    assert rb.qty_for_risk(risk, entry, sl, 0.0016, False) == risk / abs(entry - sl)


def test_overrun_grows_as_the_stop_gets_closer():
    frac = 0.0016
    wide = rb.overrun(50_000.0, 48_000.0, frac)        # SL al 4 %
    tight = rb.overrun(50_000.0, 49_750.0, frac)       # SL al 0,5 %
    assert tight > wide > 0
    assert tight == pytest.approx(frac / 0.005)
