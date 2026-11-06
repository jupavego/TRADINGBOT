"""T135 — El diario T110 con la salida adaptativa: mismas filas, con fase, motivo y versión.

La tabla no cambia: lo nuevo va en el historial de cada fila. Un arrastre que todavía no cruzó la
entrada no cuenta como «protegida»: si contara, el diario la tomaría por corrupta al leerla.
"""

from __future__ import annotations

import json
from dataclasses import replace

from eim.paper.adaptive import exit_version
from eim.paper.ladder_floor import Floor
from eim.paper.protection import OPEN, Journal, floor_of, problem
from eim.paper.protection_sync import current_ops, plan
from tests.paper.helpers import M15, T0
from tests.paper.test_adaptive_book import EP, RUN, E, adaptive_profile, run
from tests.paper.test_ladder_stop_only_book import btc

NOW = T0 + 500 * M15
PID = "moderado"
# Sube y se mantiene por encima del stop movido: la posición sigue abierta y protegida
UP = ([(E, E + 50, E - 20, E + 30)] * 2 + [(E + 30, E + 1000, E + 20, E + 990)]
      + [(E + 990, E + 1000, E + 950, E + 990)])


def books(p, rows=RUN):
    st, _ = run(p, [replace(btc(), origin="vivo")], rows)
    return {PID: st}


def rows_of(p, rows=RUN):
    """Pasada con un diario que ya existía antes de la operación."""
    ops = current_ops("BTCUSDT", books(p, rows), EP)
    return plan(Journal("BTCUSDT", first_ms=T0 - M15), ops, NOW), ops


def test_closed_operation_writes_alta_moves_and_close():
    p = adaptive_profile(k=3.0)
    res, ops = rows_of(p)
    (cur,) = ops.values()
    assert cur.close is not None and cur.close["reason"] == "SLD"
    events = [r["event"] for r in res.rows]
    assert events[0] == "alta" and events[-1] == "cierre" and "escalon" in events
    assert all(problem(r) == "" for r in res.rows)


def test_each_move_says_phase_motive_source_and_version():
    p = adaptive_profile(k=3.0)
    res, _ = rows_of(p)
    last = json.loads(res.rows[-1]["history"])
    assert last
    for h in last:
        assert h["phase"] == "arrastre" and "3·σ" in h["motive"]
        assert h["source"] == f"M2@{exit_version(p)}"
        assert h["version"] == exit_version(p) and h["features"] == "v1"


def test_open_trail_below_the_entry_is_not_protected_and_not_corrupt():
    """El stop subió, pero sigue por debajo de la entrada: abierta, no protegida, y fila válida."""
    p = adaptive_profile(k=10.0, activate_r=0.0)         # 10·σ = 1 000: arrastra sin cruzar
    rows =[(E, E + 50, E - 20, E + 30)] * 2 + [(E + 30, E + 500, E + 20, E + 490)] * 2
    res, ops = rows_of(p, rows)
    (cur,) = ops.values()
    assert cur.close is None and cur.info["active"] is False and cur.info["stop_history"]
    assert cur.info["stop"] < E
    moved = [r for r in res.rows if r["event"] == "escalon"]
    assert moved and all(r["status"] == "abierta" and r["active"] is False for r in moved)
    assert all(problem(r) == "" for r in res.rows)


def test_trail_past_the_entry_is_protected():
    p = adaptive_profile(k=1.0)
    res, ops = rows_of(p, UP)
    (cur,) = ops.values()
    assert cur.info["active"] is True and res.rows[-1]["status"] == "protegida"
    assert all(problem(r) == "" for r in res.rows)


def test_saved_row_rebuilds_a_floor_without_a_usd_level():
    p = adaptive_profile(k=1.0)
    res, _ = rows_of(p, UP)
    f = floor_of({**res.rows[-1], "seq": 2})
    assert isinstance(f, Floor) and f.protected_usd is None and f.level >= 1
    assert res.rows[-1]["status"] in OPEN


def test_ladder_profiles_keep_their_rows_exactly():
    """La escalera no pasa por nada de esto: sigue activa en cuanto el stop se mueve."""
    from eim.paper.protection_sync import _state_at
    h = {"level": 1, "stop": 1.0, "max_float": 2.0, "nominal": 3.0, "source": "escalon", "t": 4}
    assert _state_at(h)["active"] is True
