"""T131 — la interfaz `ExitPolicy` y la regresión de M0 y M1 contra el motor que midió T111.

El entregable 1 pide adaptadores que reproduzcan T111 «cifra a cifra». La forma de garantizarlo no
es comparar un informe con otro, sino demostrar que **el adaptador no cambia nada**: M0 devuelve
exactamente lo que `simulate_ladder` y M1 exactamente lo que `engine.simulate`, campo a campo, que
son las dos funciones que T111 llamó. Si eso se cumple, cualquier cifra de T111 sale igual.

Se prueban además las propiedades de §5.2 que el banco tiene que respetar con cualquier política:
determinismo, trinquete del stop, sin anticipación y precios constantes = sin cierres.
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from eim.paper.engine import Path, simulate
from eim.paper.exits.policy import ExitPolicy, LadderExit, ShadowExit, policy_fingerprint
from eim.paper.ladder import simulate_ladder
from eim.paper.params import ExecParams, LadderParams
from tests.paper.exits.helpers import COSTED, LADDER, M0, M1, SPEC, ZERO, ctx, walk_path
from tests.paper.helpers import T0, bar, flat, idea

ROWS = [(70_000, 70_400, 69_800, 70_300), (70_300, 71_200, 70_200, 71_000),
        (71_000, 71_300, 70_100, 70_200), (70_200, 70_400, 69_200, 69_300),
        (69_300, 69_500, 68_900, 69_000)]
QTY = 0.01


def _path(rows=ROWS) -> Path:
    return Path([bar(T0 + i * 900_000, *r) for i, r in enumerate(rows)])


def _same(a, b) -> None:
    """Dos `Outcome` iguales campo a campo (la idea incluida)."""
    for f in fields(a):
        assert getattr(a, f.name) == getattr(b, f.name), f.name


def test_m0_and_m1_satisfy_the_protocol():
    assert isinstance(M0, ExitPolicy)
    assert isinstance(M1, ExitPolicy)
    assert {p["id"] for p in policy_fingerprint([M0, M1])} == {"M0", "M1"}
    assert M0.params["policy"] == "ladder" and M0.params["first_r"] == LADDER.first_r
    assert M1.params["policy"] == "shadow_tp_be_time"


@pytest.mark.parametrize("ep", [ZERO, COSTED])
@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("kind,entry", [("market", 70_000.0), ("limit", 69_900.0)])
def test_m0_is_exactly_simulate_ladder(ep: ExecParams, side: int, kind: str, entry: float):
    p = _path()
    i = idea(side=side, kind=kind, entry=entry, sl=entry - side * 800, tp=entry + side * 2000,
             fill_h=2)
    got = M0.simulate(i, ctx(p, ep), QTY)
    want = simulate_ladder(i, p, ep, LADDER, QTY, None, spec=SPEC)
    _same(got, want)


@pytest.mark.parametrize("ep", [ZERO, COSTED])
@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("kind,entry", [("market", 70_000.0), ("limit", 69_900.0)])
def test_m1_is_exactly_engine_simulate(ep: ExecParams, side: int, kind: str, entry: float):
    p = _path()
    i = idea(side=side, kind=kind, entry=entry, sl=entry - side * 800, tp=entry + side * 2000,
             fill_h=2)
    _same(M1.simulate(i, ctx(p, ep), QTY), simulate(i, p, ep))


def test_m0_uses_the_fine_candles_exactly_like_the_engine():
    """Las velas de 1 min resuelven las velas ambiguas: el adaptador las pasa tal cual."""
    p = walk_path(40, seed=7)
    fine = walk_path(40 * 15, seed=7, step=60_000)
    i = idea(entry=float(p.c[0]), sl=float(p.c[0]) * 0.99, tp=float(p.c[0]) * 1.03, t=int(p.t[1]))
    got = M0.simulate(i, ctx(p, ZERO, fine), QTY)
    _same(got, simulate_ladder(i, p, ZERO, LADDER, QTY, fine, spec=SPEC))


def test_m1_overrides_only_touch_the_declared_fields():
    """Las variantes de M1 de la rejilla (`be_trigger_r`, `be_lock_r`) no tocan nada más."""
    p = _path()
    i = idea(entry=70_000.0, sl=69_200.0, tp=72_000.0)
    var = ShadowExit(overrides={"be_trigger_r": 0.5})
    assert var.params["be_trigger_r"] == 0.5
    _same(var.simulate(i, ctx(p, ZERO), QTY),
          simulate(i, p, ZERO.model_copy(update={"be_trigger_r": 0.5})))


def test_a_policy_is_deterministic_bit_for_bit():
    p = walk_path(60, seed=3)
    i = idea(entry=float(p.c[0]), sl=float(p.c[0]) * 0.985, tp=float(p.c[0]) * 1.04,
             t=int(p.t[1]))
    for pol in (M0, M1):
        a, b = pol.simulate(i, ctx(p, COSTED), QTY), pol.simulate(i, ctx(p, COSTED), QTY)
        _same(a, b)


def test_the_ladder_stop_never_loosens():
    p = walk_path(120, seed=11)
    i = idea(entry=float(p.c[0]), sl=float(p.c[0]) * 0.99, tp=float(p.c[0]) * 1.05,
             t=int(p.t[1]))
    o = M0.simulate(i, ctx(p, ZERO), QTY)
    stops = [i.sl] + [h["stop"] for h in o.ladder["stop_history"]]
    assert len(stops) > 1, "el caso tiene que mover el stop al menos una vez"
    assert all(b >= a for a, b in zip(stops, stops[1:], strict=False))


def test_flat_prices_close_nothing():
    """Propiedad 7 de §5.2: con precios constantes ninguna política cierra."""
    p = Path(flat(50, price=100.0, spread=0.0))
    i = idea(entry=100.0, sl=98.0, tp=104.0, t=int(p.t[1]))
    for pol in (M0, M1):
        o = pol.simulate(i, ctx(p, ZERO), 1.0)
        assert o.status == "ABIERTA", pol.id


def test_a_bar_cannot_move_the_stop_and_hit_it_in_the_same_bar_without_fine_candles():
    """Sin velas de 1 min manda la regla conservadora: el avance sube el stop desde la SIGUIENTE
    vela, así que la vela que dispara el escalón no puede cerrarla a ese stop (sin anticipación)."""
    px = 100.0
    rows = [(px, px, px, px), (px, px * 1.05, px * 0.995, px)]     # sube y vuelve en la misma vela
    rows += [(px, px, px * 0.9, px * 0.9)]
    p = Path([bar(T0 + k * 900_000, *r) for k, r in enumerate(rows)])
    i = idea(entry=px, sl=px * 0.98, tp=px * 1.1, t=int(p.t[1]))
    o = LadderExit(LadderParams(basis="r", first_r=0.1, step_r=0.05)).simulate(
        i, ctx(p, ZERO), 1.0)
    first = o.ladder["stop_history"][0]
    assert first["t"] == int(p.t[1]) + p.step          # confirmado al CERRAR su vela, no antes
    assert o.exit_t > first["t"]
