"""T130 — Medición honesta: MFE/MAE desde el llenado y suelo de T110 superado por velas de 1 min.

Casos reales que motivan cada prueba (`PLAN/notas/T129_sl_dinamico.md`, H6 y H7):
- entradas límite con MFE de 0,49 R y un neto máximo de −51 USDT (contaban precios anteriores al
  llenado);
- el corto del Agresivo del 2026-10-31: escalón fijado al cierre de la vela de 15 m sin velas de
  1 min completas; con ellas, el recálculo lo cerraba dentro de esa vela y quedaba «inconsistente».
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from eim.backtest.params import ZERO_COSTS
from eim.core import Candle
from eim.paper import protection
from eim.paper.book import run_profile
from eim.paper.engine import Path, simulate
from eim.paper.feedback import Learner
from eim.paper.ladder import simulate_ladder
from eim.paper.ladder_book import LadderSim
from eim.paper.ladder_floor import Floor, early
from eim.paper.params import ExecParams, LadderParams, spec_for
from eim.paper.protection_sync import run_pass
from tests.paper.helpers import M1, M15, T0, bar, fine_of, idea, walk
from tests.paper.protection_helpers import EP, MOD, NOW, OP, SYM, TOP, btc, rise, store
from tests.paper.protection_helpers import E as PE
from tests.paper.protection_helpers import path_of as prot_path
from tests.paper.protection_helpers import step as prot_step

E = 70_000.0
QTY = 0.1
ZERO = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
SPEC = spec_for("BTCUSDT")


def _path(rows: list[tuple]) -> Path:
    return Path([bar(T0 + i * M15, *r) for i, r in enumerate(rows)])


# --- MFE / MAE desde el llenado (H6) --------------------------------------------------------
LIMIT_ROWS = [(E, E + 400, E - 250, E - 150)]          # sube a +400 ANTES de bajar al límite
LIMIT_ROWS += [(E - 150, E - 130, E - 180, E - 150)] * 3
LIMIT_ROWS += [(E - 150, E - 140, E - 750, E - 700)]   # cae al SL


def test_limit_entry_mfe_ignores_prices_before_the_fill_in_both_engines():
    i = idea(kind="limit", entry=E - 200, sl=E - 700, tp=E + 1300, fill_h=4)
    sh = simulate(i, _path(LIMIT_ROWS), ZERO)
    lad = simulate_ladder(i, _path(LIMIT_ROWS), ZERO, LadderParams(), QTY, spec=SPEC)
    for o in (sh, lad):
        assert o.status == "CERRADA" and o.reason == "SL" and o.fill == E - 200
        assert o.mfe_r == pytest.approx(70 / 500)       # antes: 600/500 = 1,2 R (precio previo)
        assert o.mae_r == pytest.approx(1.0)


def test_limit_filled_and_stopped_in_the_same_candle_has_mae_to_the_stop():
    i = idea(kind="limit", entry=E - 200, sl=E - 700, tp=E + 1300, fill_h=4)
    rows = [(E, E + 400, E - 800, E - 750)] + [(E - 750, E - 740, E - 760, E - 750)] * 2
    o = simulate(i, _path(rows), ZERO)
    assert o.reason == "SL" and o.mfe_r == 0.0 and o.mae_r == pytest.approx(1.0)


def test_shadow_time_exit_does_not_count_the_candle_it_exits_at():
    flat = [(E, E + 50, E - 50, E)] * 4
    rows = flat + [(E + 10, E + 900, E - 400, E)] + flat    # vela enorme DESPUÉS de salir
    o = simulate(idea(entry=E, sl=E - 500, tp=E + 1500, hold_h=1), _path(rows), ZERO)
    assert o.reason == "TIEMPO" and o.exit == E + 10
    assert o.mfe_r == pytest.approx(0.1) and o.mae_r == pytest.approx(0.1)   # antes 1,8 y 0,8


def test_shadow_stop_exit_candle_does_not_count_its_favorable_extreme():
    rows = [(E, E + 50, E - 50, E)] * 3 + [(E, E + 1000, E - 600, E - 550)]
    o = simulate(idea(entry=E, sl=E - 500, tp=E + 1500), _path(rows), ZERO)
    assert o.reason == "SL" and o.mfe_r == pytest.approx(0.1)   # SL antes que TP: no vio +1000
    assert o.mae_r == pytest.approx(1.0)


def test_ladder_mfe_is_what_the_model_walked_alive():
    """Cuenta lo recorrido con la posición viva. Con velas de 1 min, hasta el minuto del toque: el
    escalón 2 (SL +150) salta al abrir el minuto que habría llegado a +160, así que el MFE es +150
    (antes, el máximo de la vela: +160). Con la regla conservadora, la vela que cierra por el SL
    vigente al abrir no se recorre viva."""
    bars = [(E, E + 125, E - 10, E + 125), (E + 125, E + 160, E + 90, E + 90)]
    walks = [[E, E - 10, E + 125, E + 125], [E + 125, E + 160, E + 90]]
    i = idea(entry=E, sl=E - 500, tp=E + 1500)
    fine = simulate_ladder(i, _path(bars), ZERO, LadderParams(), QTY, fine_of(walks), spec=SPEC)
    cons = simulate_ladder(i, _path(bars), ZERO, LadderParams(), QTY, spec=SPEC)
    assert fine.reason == cons.reason == "SLD"
    assert fine.exit == pytest.approx(E + 150)
    assert fine.mfe_r == pytest.approx(150 / 500) and cons.mfe_r == pytest.approx(125 / 500)


# --- suelo de T110 superado por el orden real de 1 min (H7) ---------------------------------
def _fine_candle(k: int, points: list[float]) -> Path:
    cs: list[Candle] = walk(points, T0 + k * M15)
    return Path(cs, (), M1)


def _step_fine(ps, rows, fine: Path):
    j = protection.load(ps, SYM)
    path = prot_path(rows)
    sh = [simulate(btc(), path, EP)]
    st = run_profile(MOD, sh, Learner(sh), 0.004, LadderSim(path, EP, fine, guards=j.guards))
    return st, run_pass(ps, j, {MOD.id: st}, EP, NOW)


def test_fine_close_inside_the_candle_that_set_the_floor_is_not_inconsistent():
    ps = store()
    try:
        rows = rise(6)
        prot_step(ps, rows)                            # pasada en vivo sin velas de 1 min
        saved = protection.history(ps, OP)[-1]
        floor_t = T0 + 7 * M15                         # cierre de la vela 6, la del escalón 5
        assert saved["stop"] == TOP and saved["level"] == 5 and saved["updated_t"] == floor_t
        # con las 1 min de la vela 6: sube a +465 (escalón 5) y baja a +380, bajo el SL guardado
        fine = _fine_candle(6, [PE + 385, PE + 465, PE + 380, PE + 460])
        st, res = _step_fine(ps, rows, fine)
        assert res.held == {}
        (t,) = st.trades
        assert t["reason"] == "SLD" and t["exit"] == TOP and t["exit_t"] < floor_t
        sup = t["ladder"]["floor_superseded"]
        assert sup["saved_t"] == floor_t and sup["saved_stop"] == TOP
        last = protection.history(ps, OP)[-1]
        assert last["status"] == "cerrada" and last["close_reason"] == "SLD"
        assert last["stop"] == TOP                     # el stop guardado no bajó
    finally:
        ps.close()


def test_early_keeps_holding_closes_outside_the_candle_that_set_the_floor():
    f = Floor(seq=2, t=T0 + 7 * M15, side=1, fill=PE, qty=0.017, stop=TOP, level=5,
              protected_usd=None, max_float_usd=None)
    run = SimpleNamespace(floor=f, floor_due=True, superseded=None)
    assert "antes del estado guardado" in early(run, T0 + 5 * M15)             # vela gruesa
    assert "antes del estado guardado" in early(run, T0 + 6 * M15 + 3 * M1,
                                                fine_end=T0 + 6 * M15)          # otra vela
    assert run.floor_due and run.superseded is None
    assert early(run, T0 + 6 * M15 + 3 * M1, fine_end=T0 + 7 * M15) == ""
    assert not run.floor_due and run.superseded["saved_stop"] == TOP
