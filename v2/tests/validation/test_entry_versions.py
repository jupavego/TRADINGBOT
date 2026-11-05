"""T137: las versiones de entrada. Se fija lo que falsearía la medición si fallara."""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.paper.engine import run_shadow
from eim.paper.exits import features
from eim.paper.exits import walkforward as wf
from eim.paper.exits.candidates import sigma_floor, widen_stop
from eim.paper.exits.winners_mae import fit_fold
from eim.paper.ideas import Idea
from eim.paper.params import ExecParams
from eim.paper.risk_budget import cost_r
from eim.validation import entry_run as er
from eim.validation import entry_versions as ev
from eim.validation.criteria import load_criteria
from eim.validation.entry_prereg import load_prereg
from eim.validation.gate import OBSERVACION
from eim.validation.lineage import Version, Window, iso_ms, tuning_windows
from tests.paper.exits.helpers import SPEC, coherent_path, trade
from tests.paper.helpers import M15

PR = load_prereg()
M8, S1, TOPE, M8_TOPE, S1_TOPE = PR.variants
EP = ExecParams(funding_8h_assumed=0.0)
SID = "consenso_sintesis@1h"


@pytest.fixture(scope="module")
def world():
    path, _ = coherent_path(1500, seed=7, sigma=0.002)
    return path, features.build(path, "atr14")


def _ideas(path, n=120, sl_frac=0.003, step=8, strategy="consenso_sintesis"):
    """Ideas a mercado con el SL muy cerca: la geometría y el tope tienen dónde actuar."""
    out = []
    for k in range(n):
        j = 100 + k * step
        px = float(path.c[j])
        side = 1 if k % 2 == 0 else -1
        out.append(Idea(id=f"i{k}", strategy=strategy, family="consenso", symbol="BTCUSDT",
                        t=int(path.t[j]) + M15, side=side, kind="market", entry=px,
                        sl=px - side * sl_frac * px, tp=px + side * 2 * sl_frac * px, fill_ms=0,
                        hold_ms=12 * 3_600_000, conf=0.5, why=("test",), timeframe="1h",
                        regime="range", origin="backtest"))
    return out


def _rule(v, world, quantile_of=None):
    path, atr = world
    return ev.rule_of(v, PR, atr, path.t, quantile_of, SPEC.tick)


# --- geometría y tope ----------------------------------------------------------------------------
def test_s1_moves_the_stop_exactly_as_t134_measured(world):
    """La misma función que T134: si esto cambia, lo medido ya no es la geometría con señal."""
    path, atr = world
    rule = _rule(S1, world)
    for i in _ideas(path, 30):
        got, moved, _ = rule.apply(i)
        want = widen_stop(i, sigma_floor(atr, path.t, 3.0)(i, None), SPEC.tick)
        assert got.sl == want.sl and moved == (want.sl != i.sl)
    assert any(rule.apply(i)[1] for i in _ideas(path, 30))


def test_the_stop_only_moves_outwards(world):
    path, _ = world
    rule = _rule(S1, world)
    for i in _ideas(path, 30, sl_frac=0.05):       # ya está lejos: S1 no tiene nada que hacer
        got, moved, _ = rule.apply(i)
        assert not moved and got.sl == i.sl


def test_m8_without_quantile_leaves_the_idea_alone(world):
    """«Sin muestra no se aprieta»: y eso la deja inerte, que se informa y no se esconde."""
    path, _ = world
    rule = _rule(M8, world, lambda _sid, _t: None)
    run = er.run_variant(_ideas(path, 20), rule, {}, path, EP)
    assert er.is_inert(run, SID, True)
    assert not er.is_inert(run, SID, False)


def test_cap_is_measured_on_the_stop_of_the_version(world):
    """El tope mira el SL ya apartado: M8 con el stop lejos pasa donde la idea original no."""
    path, _ = world
    i = _ideas(path, 1, sl_frac=0.004)[0]
    assert cost_r(i.entry, i.sl, PR.cost_cap.est_cost_frac) > PR.cost_cap.max_cost_r
    assert _rule(TOPE, world).apply(i)[0] is None             # la idea tal cual: vetada
    far = 0.03 * i.entry                                      # un SL del 3 % cuesta 0,053 R
    rule = replace(_rule(M8_TOPE, world, lambda _s, _t: 1e9), min_dist=lambda _i, _c: far)
    got, moved, cost = rule.apply(i)
    assert got is not None and moved and cost < PR.cost_cap.max_cost_r


def test_vetoed_idea_does_not_take_the_slot(world):
    """Una idea vetada no ocupa la plaza de la estrategia: entra la siguiente."""
    path, _ = world
    far = replace(_ideas(path, 1, sl_frac=0.05)[0], id="lejos")
    near = replace(far, id="cerca", sl=far.entry - far.side * 0.002 * far.entry)
    later = replace(far, id="luego", t=far.t + M15)
    run = er.run_variant([near, later], _rule(TOPE, world), {}, path, EP)
    closed = [t for ts in run.trades.values() for t in ts]
    assert run.stats[SID]["vetoed"] == 1 and len(closed) == 1
    assert closed[0].t == later.t


@pytest.mark.parametrize(("origin", "dt", "want"), [
    ("vivo", -1, "backtest"), ("vivo", 0, "vivo"), ("vivo", 1, "vivo"),
    ("backtest", 1, "backtest")])
def test_live_only_counts_since_the_version_exists(world, origin, dt, want):
    """Reconstruir una versión sobre un contexto en vivo anterior a ella es backtest."""
    path, _ = world
    alta = iso_ms(PR.live_rule.alta)
    i = replace(_ideas(path, 1)[0], origin=origin, t=alta + dt)
    assert _rule(S1, world).apply(i)[0].origin == want


# --- pliegues y cuantil sin fuga -----------------------------------------------------------------
def test_fold_plan_is_t134_plus_the_next_one():
    plan = ev.fold_plan(PR)
    assert set(plan) == {"15m", "1h", "4h"}
    h1 = plan["1h"]
    assert len(h1) == 11 and plan["4h"] == h1
    assert wf.iso(h1[0].fit_from) == "2023-01-11T10:00+00:00"
    assert wf.iso(h1[9].test_to) == "2026-07-11T10:00+00:00"
    assert wf.iso(h1[10].test_from) == "2026-07-11T10:00+00:00" and h1[10].test_to == ev.FAR_MS
    assert h1[10].fit_from == wf.add_months(h1[9].fit_from, 3)
    assert all(f.embargo_ms == 200 * 3_600_000 for f in h1)
    assert len(plan["15m"]) == 1
    assert wf.iso(plan["15m"][0].test_from) == "2026-10-16T14:00+00:00"


def _trade(sid, t, r=0.5, mae=0.5, exit_after=3_600_000):
    return replace(trade(r, tid=f"{sid}:{t}", policy="M1", mae=mae), t=t, sid=sid,
                   timeframe=sid.split("@")[1], exit_t=t + exit_after)


def _book(trades, min_trades=5):
    pr = PR.model_copy(update={"geometry": PR.geometry.model_copy(update={
        "m8": PR.geometry.m8.model_copy(update={"min_trades": min_trades})})})
    return ev.quantile_book(trades, lambda _t: 1.0, ev.fold_plan(pr), pr)


def test_quantile_does_not_see_its_own_test_stretch():
    """Cambiar lo que ocurre en la prueba o en el embargo no mueve el cuantil de ese pliegue."""
    f = ev.fold_plan(PR)["1h"][10]
    fit = [_trade(SID, f.fit_from + k * 86_400_000, mae=0.5) for k in range(40)]
    test = [_trade(SID, f.test_from + k * 3_600_000, mae=9.0) for k in range(40)]
    embargoed = [_trade(SID, f.fit_cut - 3_600_000, mae=7.0, exit_after=7_200_000)]
    a, b = _book(fit), _book([*fit, *test, *embargoed])
    t = f.test_from + 1
    assert a.of(SID, t) == b.of(SID, t) == pytest.approx(0.5)


def test_each_decision_uses_the_quantile_of_its_fold():
    """Un cuantil posterior no sirve para una decisión anterior, ni al revés."""
    plan = ev.fold_plan(PR)["1h"]
    early = [_trade(SID, plan[0].fit_from + k * 86_400_000, mae=0.3) for k in range(40)]
    late = [_trade(SID, plan[10].fit_from + k * 86_400_000, mae=0.9) for k in range(40)]
    book = _book([*early, *late])
    assert book.of(SID, plan[0].test_from + 1) == pytest.approx(0.3)
    assert book.of(SID, plan[10].test_from + 1) == pytest.approx(0.9)
    assert book.of(SID, plan[0].fit_from) is None     # antes del primer tramo de prueba: no hay


def test_control_takes_the_quantile_of_its_twin_and_falls_back_to_the_pool():
    """Lo que T134 no pudo: el control tiene cuantil, así que la geometría se pone a prueba."""
    f = ev.fold_plan(PR)["1h"][10]
    ctl = "control_aleatorio@1h"
    t = f.test_from + 1
    twin = [_trade(SID, f.fit_from + k * 86_400_000, mae=0.4) for k in range(40)]
    other = [_trade("otra@1h", f.fit_from + k * 86_400_000, mae=2.0) for k in range(40)]
    own = [_trade(ctl, f.fit_from + k * 86_400_000, mae=9.0) for k in range(40)]
    assert _book([*twin, *other, *own]).of(ctl, t) == pytest.approx(0.4)
    # sin gemela: el conjunto del marco, y sin las operaciones del propio control
    assert _book([*other, *own]).of(ctl, t) == pytest.approx(2.0)
    assert _book(own).of(ctl, t) is None


def test_fit_fold_is_the_one_of_t134():
    """El cuantil se calcula con la función de T134 (E5): ninguna reimplementación."""
    f = ev.fold_plan(PR)["1h"][10]
    fit = [_trade(SID, f.fit_from + k * 86_400_000, mae=0.5) for k in range(40)]
    w = fit_fold(fit, f, lambda _t: 1.0, reference="r", quantile=0.95, min_trades=5)
    assert w.of(SID) == pytest.approx(_book(fit).of(SID, f.test_from + 1))


# --- identidad: versiones, ventanas y evidencia -------------------------------------------------
def _parent() -> Version:
    win = Window(0, iso_ms("2026-10-22T22:36:00Z"), None, "auto")
    return Version(SID, 2, "padre", "consenso_sintesis", "1h", iso_ms("2026-10-22T22:36:00Z"),
                   None, "auto", windows=(win,))


def test_version_is_a_new_identity_and_changes_with_its_parameters():
    a = ev.fingerprint("padre", M8, PR, [1.0, 2.0])
    assert a == ev.fingerprint("padre", M8, PR, [1.0, 2.0])
    assert a != ev.fingerprint("padre", M8, PR, [1.0, 2.5])         # otro cuantil, otra versión
    assert a != ev.fingerprint("otro", M8, PR, [1.0, 2.0])
    assert a != ev.fingerprint("padre", M8_TOPE, PR, [1.0, 2.0])
    assert len({ev.fingerprint("padre", v, PR, []) for v in PR.variants}) == len(PR.variants)


def test_version_does_not_inherit_the_evidence_of_its_parent(world):
    """Aceptación de T137: el padre tiene operaciones y la versión solo cuenta las suyas."""
    path, _ = world
    ideas = _ideas(path, 120)
    parent_run = er.run_variant(ideas, ev.rule_of(None, PR, world[1], path.t, None, SPEC.tick),
                                {}, path, EP)
    assert parent_run.trades[SID]
    rule = _rule(S1, world)
    fp = ev.fingerprint("padre", S1, PR, [])
    child = er.run_variant(ideas, rule, {SID: fp}, path, EP)
    # 1. lo que cerró es de la versión: su SL es el apartado y su huella la nueva
    kept = [rule.apply(i)[0] for i in ideas]
    outcomes = run_shadow([replace(w, version=fp) for w in kept], path, EP)
    assert {o.idea.version for o in outcomes} == {fp}
    assert all(o.idea.sl == next(w.sl for w in kept if w.id == o.idea.id) for o in outcomes)
    # 2. con el stop más lejos no son las mismas operaciones ni el mismo resultado
    pa = {(t.t, t.exit_t, round(t.r, 9)) for t in parent_run.trades[SID]}
    ch = {(t.t, t.exit_t, round(t.r, 9)) for t in child.trades[SID]}
    assert pa != ch
    # 3. una versión sin operaciones propias tiene n = 0, aunque el padre tenga cientos
    crit = load_criteria()
    empty = er.VariantRun("s1")
    v = ev.version_of(SID, S1, PR, fp)
    r = PR.reading("reserva")
    fam = {"BTCUSDT|x": None}
    got = er.score_reading(r, [(v, "s1")], {"s1": empty, "base": parent_run}, [_parent()], fam,
                           crit, "BTCUSDT", int(path.end), None)[0]
    assert got.measure.n == 0 and got.verdict == OBSERVACION


def test_windows_of_the_parent_and_of_the_selection_exclude_trades():
    """Aplica la regla de T49 de la versión y sus ancestros, y la ventana donde se eligió."""
    v = ev.version_of(SID, M8, PR, "fp")
    wins = tuning_windows(v, [_parent()])
    sel = iso_ms(PR.windows.selection.from_) + 1
    assert any(w.covers(sel, "BTCUSDT") for w in wins)
    assert any(w.covers(iso_ms("2026-10-22T22:35:00Z"), "BTCUSDT") for w in wins)
    assert not any(w.covers(iso_ms("2026-10-23T00:00:00Z"), "BTCUSDT") for w in wins)


def test_m8_at_15m_registers_its_fit_window_and_the_others_do_not():
    w15 = ev.own_windows("x@15m", M8, PR)
    assert any(w.note == PR.windows.m8_fit_15m.note for w in w15)
    assert len(ev.own_windows("x@15m", S1, PR)) == 1 and len(ev.own_windows("x@1h", M8, PR)) == 1


def test_descriptive_reading_windows_leave_only_its_ranges():
    r = PR.reading("reserva")
    v = ev.version_of(SID, M8, PR, "fp")
    wins = ev.windows_for(r, v, [_parent()])
    inside = [iso_ms("2026-07-20T00:00:00Z"), iso_ms("2026-10-20T00:00:00Z"),
              iso_ms("2030-01-01T00:00:00Z")]
    outside = [iso_ms("2026-07-01T00:00:00Z"), iso_ms("2026-09-01T00:00:00Z")]
    assert all(not any(w.covers(t, "BTCUSDT") for w in wins) for t in inside)
    assert all(any(w.covers(t, "BTCUSDT") for w in wins) for t in outside)


def test_bank_reading_does_not_measure_15m():
    r = PR.reading("banco")
    assert ev.in_reading(r, "x@1h") and not ev.in_reading(r, "x@15m")
    assert ev.in_reading(PR.reading("oficial"), "x@15m")
