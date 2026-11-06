"""T142 — Los casos reales del escalón prematuro, con sus velas, ideas y cantidades.

`tests/fixtures/paper/t142_cases.json` trae las velas de 15 m y 1 min de BTCUSDT y las ideas tal
como ocurrieron: el falso positivo del 2026-10-31 y los dos grupos del 2026-11-04 que dejaron 5
operaciones congeladas (`PLAN/notas/T142_posiciones_fantasma.md`).

Cada caso pasa por las tres pasadas de la mesa: antes de la vela ambigua, con la vela de 15 m
cerrada y una vela de 1 min sin llegar, y con las 15 velas de 1 min. Sin `fine` la pasada se
comporta como antes de T142 y reproduce lo que pasó (mismo escalón, mismo stop, misma congelación):
eso prueba que los datos son los del fallo y que `_never_lower` sigue reteniendo lo ya mal guardado.
"""

from __future__ import annotations

import json
from pathlib import Path as FsPath

import numpy as np
import pytest

from eim.core import Candle
from eim.paper import protection
from eim.paper.account import liq_price
from eim.paper.book import ProfileState, Slot, _close
from eim.paper.engine import Path
from eim.paper.ideas import Idea
from eim.paper.ladder import simulate_ladder
from eim.paper.params import PROFILES, ExecParams, LadderParams, spec_for
from eim.paper.protection_sync import reconcile, run_pass
from tests.paper.protection_helpers import store

FIX = json.loads((FsPath(__file__).parents[1] / "fixtures" / "paper" / "t142_cases.json")
                 .read_text(encoding="utf-8"))
EP = ExecParams.model_validate(FIX["exec"])
SYM = "BTCUSDT"
M1, M15 = 60_000, 15 * 60_000
FROZEN = "el recálculo bajaría el stop guardado"
GROUPS = tuple(FIX["groups"])
PROFILE = {p.id: p for p in PROFILES}


def _op_id(op: dict) -> str:
    return protection.op_key(op["profile"], SYM, op["idea"]["id"])


def _path(g: dict, upto: int) -> Path:
    cs = [Candle(t=r[0], o=r[1], h=r[2], l=r[3], c=r[4], v=1.0)
          for r in g["candles"] if r[0] < upto]
    return Path(cs, [tuple(f) for f in g["funding"]], M15)


def _fine(g: dict, upto: int) -> Path:
    rows = [r for r in g["fine"] if r[0] < upto]
    return Path.from_arrays({k: np.array([r[n] for r in rows], dtype=float)
                             for n, k in enumerate(("t", "o", "h", "l", "c"))}, M1)


def _books(g: dict, path: Path, fine: Path, guards: dict) -> dict[str, ProfileState]:
    """Libros con las cantidades reales: el tamaño ya se decidió; aquí se prueba el diario."""
    books: dict[str, ProfileState] = {}
    for op in g["ops"]:
        pid, lp = op["profile"], LadderParams.model_validate(FIX["ladders"][op["profile"]])
        st = books.setdefault(pid, ProfileState(
            p=PROFILE[pid].model_copy(update={"ladder": lp}), equity=op["equity"]))
        i = Idea(**{**op["idea"], "why": tuple(op["idea"]["why"])})
        o = simulate_ladder(i, path, EP, lp, op["qty"], fine, spec=spec_for(SYM),
                            guard=guards.get((pid, i.id)))
        if o.fill_t is None or o.status not in ("ABIERTA", "CERRADA"):
            continue
        margin = op["qty"] * o.fill / op["leverage"]
        st.slots[i.id] = Slot(o, op["qty"], op["leverage"], margin, 1.0,
                              op["qty"] * abs(o.fill - i.sl), filled=True,
                              liq=liq_price(i.side, o.fill, op["leverage"], 0.004),
                              base=op["equity"])
        st.used += margin
        if o.status == "CERRADA":
            _close(st, o)
    return books


def _pass(ps, g: dict, upto_15m: int, upto_1m: int, *, gated: bool = True):
    """Una pasada como la de la mesa: lee el diario, recalcula y lo pone al día."""
    path, fine = _path(g, upto_15m), _fine(g, upto_1m)
    j = protection.load(ps, SYM)
    books = _books(g, path, fine, j.guards)
    return books, run_pass(ps, j, books, EP, upto_15m + M1, fine=fine if gated else None)


def _rows(ps, op: dict) -> list[dict]:
    return protection.history(ps, _op_id(op))


def _never_went_down(rows: list[dict], side: int) -> bool:
    return all((b["stop"] - a["stop"]) * side >= -1e-9
               for a, b in zip(rows, rows[1:], strict=False))


@pytest.fixture
def ps():
    s = store()
    yield s
    s.close()


@pytest.mark.parametrize("name", GROUPS)
def test_step_of_a_candle_without_its_minutes_waits_and_nothing_freezes(ps, name):
    g = FIX["groups"][name]
    bar, close = g["bar"], g["bar"] + M15
    _pass(ps, g, bar, bar)                                    # antes de la vela ambigua
    before = {_op_id(op): _rows(ps, op)[-1]["stop"] for op in g["ops"]}

    _, early = _pass(ps, g, close, close - M1)                # 15 m cerrada, falta 1 vela de 1 min
    assert early.held == {}
    assert set(early.waiting) == {_op_id(op) for op in g["ops"]}
    for op in g["ops"]:                                       # el escalón prematuro no se guardó
        assert _rows(ps, op)[-1]["stop"] == before[_op_id(op)]
        assert _rows(ps, op)[-1]["updated_t"] < close

    _, done = _pass(ps, g, close, close)                      # ya con las 15 velas
    assert done.held == {} and done.waiting == []
    for op in g["ops"]:
        rows = _rows(ps, op)
        assert all(r["status"] != "inconsistente" for r in rows)
        assert _never_went_down(rows, op["idea"]["side"])


@pytest.mark.parametrize("name", GROUPS)
def test_real_close_is_recorded_with_its_real_price_and_time(ps, name):
    g = FIX["groups"][name]
    bar, close = g["bar"], g["bar"] + M15
    end = max(r[0] for r in g["candles"]) + M15
    _pass(ps, g, bar, bar)
    _pass(ps, g, close, close - M1)
    _pass(ps, g, close, close)
    books, res = _pass(ps, g, end, end)
    assert res.held == {} and res.waiting == []
    for op in g["ops"]:
        last, want = _rows(ps, op)[-1], op["expected"]
        assert (last["status"], last["close_reason"]) == ("cerrada", want["reason"])
        assert last["exit_price"] == pytest.approx(want["exit"])
        assert last["exit_t"] == want["exit_t"]
        (t,) = [t for t in books[op["profile"]].trades if t["id"] == op["idea"]["id"]]
        assert t["ladder"]["floor_superseded"] is None        # no hubo suelo que superar


@pytest.mark.parametrize("name", GROUPS)
def test_without_the_gate_it_saves_the_real_premature_step(ps, name):
    g = FIX["groups"][name]
    bar, close = g["bar"], g["bar"] + M15
    _pass(ps, g, bar, bar, gated=False)
    _pass(ps, g, close, close - M1, gated=False)
    for op in g["ops"]:
        last = _rows(ps, op)[-1]
        assert (last["level"], last["stop"], last["updated_t"]) == (
            op["saved"]["level"], op["saved"]["stop"], op["saved"]["t"])


@pytest.mark.parametrize("name", GROUPS)
def test_never_lower_still_holds_a_premature_step_already_saved(ps, name):
    """Lo guardado antes de T142 sigue retenido: la salvaguarda no se afloja, ni con la espera."""
    g = FIX["groups"][name]
    bar, close = g["bar"], g["bar"] + M15
    _pass(ps, g, bar, bar, gated=False)
    _pass(ps, g, close, close - M1, gated=False)              # el código viejo guarda el escalón
    _, res = _pass(ps, g, close, close)                       # el nuevo ya tiene las 15 velas
    want = {_op_id(op) for op in g["ops"] if op["freezes"]}
    assert set(res.held) == want
    assert all(res.held[k] == FROZEN for k in want)
    for op in g["ops"]:
        rows = _rows(ps, op)
        assert _never_went_down(rows, op["idea"]["side"])
        if op["freezes"]:                                     # sin cierre y con el stop guardado
            assert rows[-1]["status"] == "inconsistente"
            assert rows[-1]["stop"] == op["saved"]["stop"]


@pytest.mark.parametrize("name", GROUPS)
def test_reconciling_closes_them_at_the_price_the_ledger_already_has(ps, name):
    """El ◆ de T142 sobre los datos reales: `recalculo` y la pasada siguiente cierra."""
    g = FIX["groups"][name]
    bar, close = g["bar"], g["bar"] + M15
    _pass(ps, g, bar, bar, gated=False)
    _pass(ps, g, close, close - M1, gated=False)
    _pass(ps, g, close, close, gated=False)
    frozen = [op for op in g["ops"] if op["freezes"]]
    for op in frozen:
        assert _rows(ps, op)[-1]["status"] == "inconsistente"
        reconcile(ps, _op_id(op), "recalculo", "falso positivo T142", close + M1)
    _, res = _pass(ps, g, close, close)
    assert res.held == {}
    for op in frozen:
        last, want = _rows(ps, op)[-1], op["expected"]
        assert last["status"] == "cerrada" and last["exit_t"] == want["exit_t"]
        assert last["exit_price"] == pytest.approx(want["exit"])


def test_the_real_cases_are_the_five_that_froze():
    frozen = [op for g in FIX["groups"].values() for op in g["ops"] if op["freezes"]]
    assert sorted((op["profile"], op["saved"]["stop"]) for op in frozen) == [
        ("agresivo", 77_043.5), ("moderado", 77_043.5), ("moderado", 80_882.7),
        ("moderado", 80_911.7), ("ppp_btcusdt", 77_116.6)]
