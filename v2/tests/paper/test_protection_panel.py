"""T112 — Lo que el panel de protección lee del resumen: neto estimado si salta el stop vigente,
último escalón alcanzado y violaciones recientes (caminos sintéticos, sin red)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.paper.book import _reject
from eim.paper.feedback import Learner
from eim.paper.ladder_stats import last_step
from eim.paper.params import ExecParams
from eim.paper.summary import RECENT_VIOLATIONS, profile_summary
from tests.paper.helpers import M15, T0
from tests.paper.test_ladder_book import UP, build
from tests.paper.test_ladder_stop_only import CASES, QTY, D, climb, run, steps


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_under_the_initial_stop_the_estimate_is_the_full_loss(pid, side):
    """Sin activar la protección, si salta el stop se pierde el riesgo entero (sin costos)."""
    f, _ = steps(pid)
    o = run(pid, side, [(0, 0.8 * f, -10, 0.5 * f)])
    assert o.ladder["state"] == "inicial"
    assert o.ladder["stop_est_usd"] == pytest.approx(-QTY * D)


@pytest.mark.parametrize(("pid", "side"), CASES)
def test_with_protection_the_estimate_covers_the_protected_level(pid, side):
    """Con la protección activa el neto estimado del stop vigente cubre el nivel protegido, y con
    costos reales queda por debajo del flotante: lo protegido no es lo flotante."""
    f, st = steps(pid)
    o = run(pid, side, climb(f, st))
    assert o.ladder["state"] == "protegida" and o.ladder["level"] == 3
    assert o.ladder["stop_est_usd"] == pytest.approx(o.ladder["nominal_usd"], abs=QTY * 0.1)
    c = run(pid, side, [(0, 30, -1, 29)], ep=ExecParams())     # sube ≈ 30 USDT brutos
    assert c.ladder["state"] == "protegida" and c.ladder["level"] >= 1
    assert c.ladder["nominal_usd"] - 1e-9 <= c.ladder["stop_est_usd"] < c.ladder["float_usd"]


def test_last_step_is_the_latest_stop_move_among_open_and_closed():
    closed = {"id": "a", "sid": "s1", "ladder": {"stop_history": [
        {"t": 10, "level": 1, "nominal": 5.0, "source": "escalon"},
        {"t": 30, "level": 2, "nominal": 7.5, "source": "escalon"}]}}
    open_ = {"id": "b", "sid": "s2", "ladder": {"stop_history": [
        {"t": 20, "level": 1, "nominal": 4.0, "source": "escalon"}]}}
    assert last_step([closed], [open_]) == {"t": 30, "level": 2, "nominal_usd": 7.5,
                                            "source": "escalon", "id": "a", "sid": "s1",
                                            "open": False}
    open_["ladder"]["stop_history"].append({"t": 40, "level": 2, "nominal": 6.0, "source": "be"})
    got = last_step([closed], [open_])
    assert got["open"] and got["id"] == "b" and got["source"] == "be"
    assert last_step([{"id": "c", "sid": "s", "ladder": {"stop_history": []}}], []) is None
    assert last_step([{"id": "c", "sid": "s"}], []) is None      # cierre sin escalera


def test_summary_exposes_the_open_estimate_last_step_and_recent_violations():
    st = build(UP[:3])                                # sube y protege; aún no retrocede
    (pos,) = st.slots.values()
    for k in range(RECENT_VIOLATIONS + 2):            # cierres prohibidos: no se ejecutan
        _reject(st, replace(pos.o, reason="TP", exit_t=T0 + (5 + k) * M15), "TP fijo prohibido")
    sm = profile_summary(st, Learner([]), [], T0 + 20 * M15, 0.004)
    (p,) = sm["positions"]
    lad = p["ladder"]
    assert lad["state"] == "protegida" and lad["stop_est_usd"] >= lad["nominal_usd"] - 1e-9
    assert sm["ladder"]["last_step"]["open"] and sm["ladder"]["last_step"]["id"] == p["id"]
    assert sm["ladder"]["last_step"]["level"] == lad["level"]
    recent = sm["ladder"]["violations_recent"]
    assert len(recent) == RECENT_VIOLATIONS and sm["counts"]["violations"] == RECENT_VIOLATIONS + 2
    assert recent[-1]["t"] == T0 + (5 + RECENT_VIOLATIONS + 1) * M15
    assert all(not v["executed"] for v in recent)


def test_close_events_carry_their_exact_reason_and_an_estimated_level():
    """La bitácora distingue stop inicial y dinámico por el motivo del evento, y el texto dice que
    el nivel protegido es una estimación (lo realizado puede quedar por debajo)."""
    st = build(UP)
    (t,) = st.trades
    close = st.events[-1]
    assert close["cat"] == "sl" and close["reason"] == t["reason"] == "SLD"
    assert "nivel protegido" in close["text"] and "estimado" in close["text"]
    assert "protegidos" not in close["text"]
