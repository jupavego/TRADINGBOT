"""T110 — Diario de la protección: el escalón sobrevive a un reinicio y nunca baja.

Casos del encargo: H (reinicio con posición abierta y protección activa: el nivel se conserva),
instantánea por detrás o por delante de lo recalculado (se adopta la mayor, con aviso), instantánea
corrupta o ausente (estado inconsistente, sin cierre inventado) e historial completo tras varios
escalones. Un «reinicio» es leer el diario de nuevo y recalcular desde cero, como la mesa.
"""

from __future__ import annotations

import json

import pytest

from eim.paper import protection
from eim.paper.protection_sync import GONE, current_ops, plan
from tests.paper.helpers import M15, T0
from tests.paper.protection_helpers import (
    EP,
    MOD,
    OP,
    TOP,
    E,
    book,
    btc,
    insert_copy,
    pullback,
    rise,
    step,
    stops,
    store,
)


@pytest.fixture
def ps():
    s = store()
    yield s
    s.close()


def _pos(st):
    (s,) = st.slots.values()
    return s.o.ladder


def test_case_h_restart_keeps_level_and_stop(ps):
    st1, r1 = step(ps, rise(6))
    saved = protection.history(ps, OP)[-1]
    assert _pos(st1)["level"] == 5 and saved["level"] == 5 and saved["stop"] == TOP
    assert saved["status"] == "protegida" and r1.open_ids == {OP}
    # «reinicio»: diario leído de nuevo, todo recalculado desde cero, más velas quietas
    st2, r2 = step(ps, rise(6, flat=8), now=r1.first_ms + 3_600_000, startup=True)
    assert r2.rows == [] and r2.recovered == [] and r2.ahead == [] and r2.held == {}
    assert _pos(st2)["level"] == 5 and _pos(st2)["stop"] == TOP
    assert protection.history(ps, OP)[-1] == saved          # misma fila vigente, nada reescrito


def test_case_h_restart_with_lower_recompute_keeps_saved_step(ps):
    """Tras el reinicio el recálculo da menos (escalera con otro incremento): manda lo guardado
    y, si el precio vuelve, cierra en el SL guardado, no en el recalculado."""
    step(ps, rise(6))
    wider = MOD.model_copy(update={"ladder": MOD.ladder.model_copy(update={"step_r": 0.15})})
    alone, _ = book(None, rise(6), wider)                     # sin diario: SL más bajo
    assert alone.slots[btc().id].o.ladder["stop"] < TOP
    seen: set = set()
    st, res = step(ps, rise(6), p=wider, startup=True, seen=seen)
    lad = _pos(st)
    assert lad["stop"] == TOP and lad["stop_source"] == "recuperado"
    assert lad["recovered"]["from_stop"] < TOP == lad["recovered"]["to_stop"]
    assert [r["op_id"] for r in res.recovered] == [OP] and seen == {OP}
    assert protection.history(ps, OP)[-1]["event"] == "recuperacion"
    st, res = step(ps, pullback(rise(6), TOP - 20), p=wider, seen=seen)
    (t,) = st.trades
    assert t["reason"] == "SLD" and t["exit"] == TOP              # cierra en el SL guardado
    assert "SL recuperado del diario" in st.events[-1]["text"]
    assert res.recovered == []                                    # avisada una vez por proceso
    last = protection.history(ps, OP)[-1]
    assert last["status"] == "cerrada" and last["close_reason"] == "SLD" and last["stop"] == TOP


def test_snapshot_behind_recompute_adopts_recompute_with_notice(ps):
    step(ps, rise(3, flat=0))
    assert protection.history(ps, OP)[-1]["level"] == 2
    st, res = step(ps, rise(6), startup=True)                   # siguió subiendo mientras paraba
    assert _pos(st)["level"] == 5 and _pos(st).get("recovered") is None
    assert [(r["from_level"], r["to_level"], r["changes"]) for r in res.ahead] == [(2, 5, 3)]
    rows = protection.history(ps, OP)
    assert [r["event"] for r in rows] == ["alta"] + ["escalon"] * 5
    assert rows[-1]["stop"] == TOP and rows[-1]["level"] == 5


def test_history_is_complete_one_row_per_change_and_append_only(ps):
    step(ps, rise(6))
    step(ps, pullback(rise(6), TOP - 20))
    rows = protection.history(ps, OP)
    assert [r["event"] for r in rows] == ["alta"] + ["escalon"] * 5 + ["cierre"]
    assert [r["seq"] for r in rows] == list(range(1, 8))
    assert [len(json.loads(r["history"])) for r in rows] == [0, 1, 2, 3, 4, 5, 5]
    assert [r["level"] for r in rows] == [0, 1, 2, 3, 4, 5, 5]
    s = stops(ps)
    assert s[0] == E - 1400 and all(b > a for a, b in zip(s[:-2], s[1:-1], strict=True))
    assert s[-1] == TOP and rows[-1]["exit_price"] == TOP and rows[-1]["close_reason"] == "SLD"
    first = rows[1]
    assert first["active"] and first["protected_usd"] > 0 and first["max_float_usd"] > 0
    assert json.loads(first["costs"])["slip_reserve_bars"] == MOD.ladder.slip_lookback
    assert step(ps, pullback(rise(6), TOP - 20), now=T0 + 999 * M15)[1].rows == []
    assert protection.history(ps, OP) == rows                    # nada reescrito ni duplicado


def test_missing_snapshot_is_inconsistent_without_inventing_a_close(ps):
    step(ps, rise(6))
    ps.execute("DELETE FROM paper_protection WHERE op_id = ?", [OP])   # la instantánea se perdió
    st, res = step(ps, pullback(rise(6), TOP - 20))
    assert st.trades == [] and btc().id in st.slots              # el SL se tocó, pero no se cierra
    lad = _pos(st)
    assert lad["state"] == "inconsistente" and lad["stop"] == TOP   # el stop no se toca
    assert res.held == {OP: protection.MISSING}
    (row,) = protection.history(ps, OP)
    assert row["status"] == protection.HELD and row["close_reason"] is None
    assert step(ps, pullback(rise(6), TOP - 20))[1].rows == []   # congelada hasta reconciliarla


@pytest.mark.parametrize(("change", "why"), [
    ({"history": "{roto"}, "historial"),
    ({"stop": None}, "stop ausentes"),
    ({"symbol": "ETHUSDT"}, "símbolo"),
])
def test_corrupt_snapshot_is_inconsistent_and_stop_untouched(ps, change, why):
    step(ps, rise(6))
    insert_copy(ps, **change)
    st, res = step(ps, pullback(rise(6), TOP - 20))
    assert st.trades == [] and _pos(st)["state"] == "inconsistente"
    assert _pos(st)["stop"] == TOP and _pos(st)["stop_source"] == "escalon"   # el del recálculo
    assert why in res.held[OP] and "corrupta" in res.held[OP]
    last = protection.history(ps, OP)[-1]
    assert last["event"] == "inconsistente" and last["stop"] == TOP


def test_snapshot_that_does_not_match_the_operation_is_inconsistent(ps):
    step(ps, rise(6))
    insert_copy(ps, entry=E + 50.0)
    st, res = step(ps, pullback(rise(6), TOP - 20))
    assert st.trades == [] and "no cuadra" in res.held[OP]
    assert protection.history(ps, OP)[-1]["entry"] == E + 50.0   # se copia lo guardado tal cual


def test_recompute_closing_before_the_saved_instant_is_not_a_close(ps):
    """El recálculo (velas corregidas) cerraría en la vela 3, pero la instantánea vio la operación
    viva y en el escalón 5 al final de la vela 6: no se inventa ese cierre."""
    step(ps, rise(6))
    rows = rise(6)
    rows[3] = (rows[3][0], rows[3][1], E + 100, rows[3][3])        # mínimo bajo el SL del escalón 1
    alone, _ = book(None, rows)
    assert alone.trades and alone.trades[0]["exit_t"] < protection.history(ps, OP)[-1]["updated_t"]
    st, res = step(ps, rows)
    assert st.trades == [] and _pos(st)["stop"] == TOP
    assert "antes del estado guardado" in res.held[OP]


def test_saved_operation_missing_from_recompute_and_closed_reopened(ps):
    step(ps, rise(6))
    _st, res = step(ps, rise(6), ideas=[])
    assert res.held == {OP: GONE}
    other = store()
    step(other, rise(6))
    step(other, pullback(rise(6), TOP - 20))                       # guardada como cerrada
    j = protection.load(other, "BTCUSDT")
    st, _ = book(None, rise(6))                                    # … y abierta al recalcular
    res = plan(j, current_ops("BTCUSDT", {"moderado": st}, EP), T0)
    assert "guardada como cerrada" in res.held[OP]
    other.close()


def test_no_automatic_row_lowers_the_saved_stop(ps):
    """Invariante: en el diario, el SL de una operación solo sube (salvo filas inconsistentes)."""
    step(ps, rise(3, flat=0))
    step(ps, rise(6), startup=True)
    wider = MOD.model_copy(update={"ladder": MOD.ladder.model_copy(update={"step_r": 0.15})})
    step(ps, rise(6), p=wider)
    step(ps, pullback(rise(6), TOP - 20), p=wider)
    s = stops(ps)
    assert all(b >= a for a, b in zip(s, s[1:], strict=False)) and s[-1] == TOP
