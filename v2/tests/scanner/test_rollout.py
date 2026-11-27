"""T102 — despliegue gradual: desactivación y reactivación automáticas, sombra y promoción por
criterios (hoy bloqueada por T101, T96 y T103; la ejecución limitada nunca es automática)."""

from __future__ import annotations

import copy

from eim.scanner import health as H
from eim.scanner import rollout as R
from tests.scanner._t102 import DAY, NOW, STATUS, make_view

NO_GATES: dict = {"t101": {"available": False}, "t96_built": False, "t103_built": False}
ALL_GATES = {"t101": {"available": True, "cells": {"crypto": "publicable"}},
             "t96_built": True, "t103_built": True}


def _check(state, view, now, gates=NO_GATES):
    return R.evaluate(state, H.build(view, STATUS, now), view, gates, now)


def test_units_start_in_alert_and_say_what_blocks_them():
    st, ch = _check(None, make_view(), NOW)
    u = st["units"]["class:crypto"]
    assert u["level"] == "alerta" and u["active"] and ch == []
    assert any("T101" in b for b in u["next"]) and any("T96" in b for b in u["next"])
    assert "class:bond" not in st["units"] and "agent:ema" not in st["units"]   # 3 < 5 corridas


def test_a_class_is_deactivated_after_two_bad_checks_and_its_candidates_go_to_shadow():
    v = make_view()
    st, _ = _check(None, v, NOW)
    st, ch = _check(st, v, NOW + 4 * DAY)                    # obsoleta 1
    assert st["units"]["class:crypto"]["active"] and ch == []
    st, ch = _check(st, v, NOW + 5 * DAY)                    # obsoleta 2 → fuera
    u = st["units"]["class:crypto"]
    assert not u["active"] and [c["what"] for c in ch if c["unit"] == "class:crypto"] == \
        ["desactivada"]
    assert R.shadow_reason(v["opportunities"][0], st).startswith("clase desactivada")
    fresh = make_view(now=NOW + 5 * DAY)
    st, _ = _check(st, fresh, NOW + 5 * DAY)
    assert not st["units"]["class:crypto"]["active"]          # una sana no basta
    st, ch = _check(st, fresh, NOW + 5 * DAY + 1)
    assert st["units"]["class:crypto"]["active"] and st["units"]["class:crypto"]["level"] == \
        "alerta" and any(c["what"] == "reactivada" for c in ch)
    assert R.shadow_reason(v["opportunities"][0], st) is None


def test_an_agent_with_no_data_is_deactivated_but_degraded_is_not():
    v = make_view(shortlist=6, agent_status={"ema": "no_data", "structure": "degraded"})
    st, _ = _check(None, v, NOW)
    st, _ = _check(st, v, NOW + 1)
    assert not st["units"]["agent:ema"]["active"] and st["units"]["agent:structure"]["active"]
    # ema pesa 0,3 de 0,45: la candidata queda en sombra; con poco peso, no
    assert "ema" in R.shadow_reason(v["opportunities"][0], st)
    light = copy.deepcopy(v["opportunities"][0])
    light["synthesis"]["contributions"] = {"ema": 0.05, "structure": 0.3, "levels": 0.3}
    assert R.shadow_reason(light, st) is None


def test_promotion_is_automatic_only_when_every_criterion_holds():
    v = make_view(above=1)
    st = None
    for k in range(R.PROMOTE_MIN_OK_CHECKS):
        st, ch = _check(st, v, NOW + k)
    assert st["units"]["class:crypto"]["level"] == "alerta"   # sin T101/T96 no sube
    st, ch = _check(st, v, NOW + 100, ALL_GATES)
    u = st["units"]["class:crypto"]
    assert u["level"] == "simulacion" and any(c["what"] == "promovida" for c in ch)
    assert any("días en simulación" in b for b in u["next"])
    later = NOW + (R.SIM_MIN_DAYS + 1) * DAY
    st, _ = _check(st, make_view(above=1, now=later), later, ALL_GATES)
    assert st["units"]["class:crypto"]["level"] == "simulacion"   # faltan resultados maduros
    assert any("resultados maduros" in b for b in st["units"]["class:crypto"]["next"])


def test_paper_never_jumps_to_limited_execution_and_a_drop_resets_to_alert():
    u = R.new_unit("class", "crypto", NOW)
    u["level"] = "papel"
    assert R.blockers(u, None, H.build(make_view(), STATUS, NOW), ALL_GATES, NOW) == \
        [R.NEVER_AUTO]
    st = {"version": "1", "units": {"class:crypto": dict(u, level="simulacion")}}
    v = make_view()
    st, _ = _check(st, v, NOW + 4 * DAY)
    st, ch = _check(st, v, NOW + 5 * DAY)
    assert st["units"]["class:crypto"]["level"] == "alerta"
    assert [c["what"] for c in ch if c["unit"] == "class:crypto"] == ["bajada", "desactivada"]


def test_evaluate_does_not_mutate_the_previous_state():
    st, _ = _check(None, make_view(), NOW)
    before = copy.deepcopy(st)
    _check(st, make_view(), NOW + 4 * DAY)
    assert st == before
