"""T142 — Qué espera el diario de la protección hasta tener las velas de 1 min."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import numpy as np
import pytest

from eim.paper import protection
from eim.paper.engine import Path
from eim.paper.protection_desk import DeskProtection
from eim.paper.protection_ops import Cur
from eim.paper.protection_settle import HOLE_WAIT_MS, gate, settled
from eim.paper.protection_sync import current_ops, plan, run_pass
from tests.paper.helpers import M1, M15, T0
from tests.paper.protection_helpers import EP, OP, SYM, book, pullback, rise, sim_book, step, store

BAR = T0 - T0 % M15          # múltiplo de 15 m (las velas de los helpers no tienen por qué serlo)


def fine_at(minutes: list[int], t0: int = BAR) -> Path:
    """Velas de 1 min planas en los minutos pedidos, contados desde `t0`."""
    ts = np.array([t0 + m * M1 for m in minutes], dtype=float)
    one = np.ones(len(ts))
    return Path.from_arrays({"t": ts, "o": one, "h": one, "l": one, "c": one}, M1)


def cur(hist: list[dict], close: dict | None = None, **info) -> Cur:
    return Cur("o", "p", SYM, "i", 1, 100.0, 1.0, 90.0, BAR, {
        "stop_history": hist, "level": len(hist), "stop": hist[-1]["stop"] if hist else 90.0,
        "max_float_usd": 9.0, "stop_source": hist[-1]["source"] if hist else "inicial",
        "first_usd": 1.0, "step_usd": 1.0, **info}, {}, close)


def h(t: int, stop: float, source: str = "escalon", **kw) -> dict:
    return {"t": t, "level": 1, "nominal": 1.0, "stop": stop, "max_float": 2.0, "source": source,
            **kw}


@pytest.fixture
def ps():
    s = store()
    yield s
    s.close()


# --- la puerta -------------------------------------------------------------------------------
@pytest.mark.parametrize("fine", [None, fine_at([])])
def test_without_minute_candles_there_is_nothing_to_wait_for(fine):
    assert gate(fine, EP) is None
    c = cur([h(BAR + M15, 91.0)])
    assert settled(c, None) == (c, False)


def test_a_candle_is_ready_only_with_all_its_minutes():
    close = BAR + M15
    assert not gate(fine_at(list(range(14))), EP)(close)         # falta la última
    assert gate(fine_at(list(range(15))), EP)(close)
    assert gate(fine_at(list(range(15))), EP)(BAR + 3 * M1)      # instante dentro de esa vela


def test_a_late_tail_waits_without_limit():
    late = BAR + 500 * M15                                        # muy por delante de la cola
    assert not gate(fine_at(list(range(15))), EP)(late)


def test_a_hole_waits_until_the_tail_passes_it_by_the_limit():
    wait = HOLE_WAIT_MS // M1
    hole = [m for m in range(15 + wait) if m != 7]                # falta el minuto 7
    assert not gate(fine_at(hole[:-1]), EP)(BAR + M15)            # la cola aún no lo rebasa
    assert gate(fine_at(hole), EP)(BAR + M15)                     # ya no se va a rellenar


def test_a_candle_with_invalid_minutes_is_not_ready():
    fine = fine_at(list(range(15)))
    fine.h[3] = np.nan
    assert not gate(fine, EP)(BAR + M15)


# --- el recorte --------------------------------------------------------------------------------
def test_settled_keeps_what_cannot_change_and_cuts_from_the_first_that_can():
    ready = lambda t: t <= BAR + M15                              # noqa: E731
    a, b = h(BAR + M15, 91.0, active=True), h(BAR + 2 * M15, 92.0)
    got, waits = settled(cur([a, b, h(BAR + 3 * M15, 93.0)]), ready)
    assert waits and got.info["stop_history"] == [a]
    assert (got.info["stop"], got.info["level"], got.info["active"]) == (91.0, 1, True)
    assert got.info["stop_source"] == "escalon" and got.info["max_float_usd"] == 2.0


def test_settled_with_nothing_ready_leaves_the_initial_state():
    got, waits = settled(cur([h(BAR + M15, 91.0)]), lambda t: False)
    assert waits and got.info["stop_history"] == []
    assert (got.info["stop"], got.info["level"], got.info["active"]) == (90.0, 0, False)
    assert got.info["stop_source"] == "inicial" and got.info["max_float_usd"] is None


def test_settled_holds_a_close_of_a_candle_without_its_minutes():
    close = {"reason": "SLD", "exit": 91.0, "exit_t": BAR + 2 * M15, "pnl": 1.0}
    ready = lambda t: t <= BAR + M15                              # noqa: E731
    got, waits = settled(cur([h(BAR + M15, 91.0)], close), ready)
    assert waits and got.close is None and len(got.info["stop_history"]) == 1
    assert settled(cur([h(BAR + M15, 91.0)], close), lambda t: True)[0].close == close


def test_settled_ignores_steps_recovered_from_the_journal():
    """Un suelo recuperado no sale del 1 min: no hace esperar."""
    c = cur([h(BAR + 5 * M15, 91.0, "recuperado")])
    assert settled(c, lambda t: False) == (c, False)


# --- la pasada ---------------------------------------------------------------------------------
def _step_fine(ps, rows, fine, **kw):
    st, j = book(ps, rows)
    return st, run_pass(ps, j, {st.p.id: st}, EP, T0 + 400 * M15, fine=fine, **kw)


def test_the_entry_is_saved_even_if_its_steps_wait(ps):
    st, res = _step_fine(ps, rise(6), fine_at([0]))               # 1 min muy por detrás
    assert res.waiting == [OP] and res.held == {} and OP in res.open_ids
    (row,) = protection.history(ps, OP)
    assert (row["event"], row["status"], row["level"]) == ("alta", "abierta", 0)
    assert st.slots[next(iter(st.slots))].o.ladder["level"] == 5  # la vista no cambia


def test_steps_that_waited_are_saved_as_they_would_have_been(ps):
    """Sin nada ambiguo, esperar no cambia ni los escalones, ni su instante ni su stop."""
    other = store()
    try:
        step(other, rise(6))
        _step_fine(ps, rise(6), fine_at([0]))
        _, res = _step_fine(ps, rise(6), None)
        assert res.waiting == []
        keys = ("seq", "event", "status", "level", "stop", "updated_t", "protected_usd")
        assert ([[r[k] for k in keys] for r in protection.history(ps, OP)]
                == [[r[k] for k in keys] for r in protection.history(other, OP)])
    finally:
        other.close()


def test_a_close_that_waits_stays_open_in_the_journal_and_is_saved_later(ps):
    rows = pullback(rise(6), 69_000.0)
    step(ps, rise(6))                                             # ya con su suelo guardado
    st, j = book(ps, rows)
    assert st.trades                                              # la vista la ve cerrada
    res = run_pass(ps, j, {st.p.id: st}, EP, T0 + 400 * M15, fine=fine_at([0]))
    assert res.waiting == [OP] and OP in res.open_ids and res.rows == []
    assert protection.history(ps, OP)[-1]["status"] == "protegida"
    st, j = book(ps, rows)
    res = run_pass(ps, j, {st.p.id: st}, EP, T0 + 400 * M15)
    assert protection.history(ps, OP)[-1]["status"] == "cerrada" and OP not in res.open_ids


def test_a_saved_close_is_not_reported_inconsistent_while_a_candle_waits(ps):
    """Lo ya cerrado no pasa por la puerta: si no, parecería abierta al recalcular."""
    rows = pullback(rise(6), 69_000.0)
    step(ps, rise(6))
    step(ps, rows)
    assert protection.history(ps, OP)[-1]["status"] == "cerrada"
    st, j = book(ps, rows)
    res = plan(j, current_ops(SYM, {st.p.id: st}, EP), T0 + 400 * M15, ready=lambda t: False)
    assert res.held == {} and res.rows == [] and res.waiting == []


def test_view_reports_what_is_waiting(ps):
    class Desk(DeskProtection):
        def __init__(self):
            self.pstore, self.ep, self.alerts = ps, EP, None
            self._lock, self._cache = threading.Lock(), {}
            self._protection_init()

    d = Desk()
    st = sim_book(rise(6), guards=d._guards(SYM))
    v = SimpleNamespace(symbol=SYM, books={st.p.id: st}, protection={})
    d._sync_protection(v, fine_at([0]))
    assert v.protection["waiting_fine"] == [OP] and v.protection["n_inconsistent"] == 0
    st = sim_book(rise(6), guards=d._guards(SYM))
    v = SimpleNamespace(symbol=SYM, books={st.p.id: st}, protection={})
    d._sync_protection(v)
    assert v.protection["waiting_fine"] == []
    assert protection.history(ps, OP)[-1]["level"] == 5
