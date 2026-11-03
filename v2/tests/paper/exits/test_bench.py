"""T131 — el banco emparejado: mismas entradas, mismo tamaño, solo cambia la salida.

Incluye la comprobación de aceptación del **control aleatorio**: con entradas al azar y el mismo
riesgo, ninguna salida puede ser rentable. Si lo fuera, habría un error o anticipación en el banco.
La prueba se hace sobre paseos aleatorios INDEPENDIENTES (un camino, una idea), porque varias
ideas del mismo camino se solapan y su error estándar aparente sería mucho menor que el real: con
esa trampa cualquier ruido parece significativo.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.paper.exits import bench
from eim.paper.exits.policy import ShadowExit
from tests.paper.exits.helpers import (
    COSTED,
    M0,
    M1,
    SPEC,
    ZERO,
    ctx,
    random_ideas,
    walk_path,
)
from tests.paper.helpers import T0, idea

PATHS = 240            # caminos independientes del control
BARS = 320
SEED = 5000
RISK = 100.0


def test_the_fixed_size_comes_from_the_declared_geometry_and_the_instrument_step():
    i = idea(entry=70_000.0, sl=69_300.0)         # 700 USDT de distancia
    q = bench.qty_for(i, SPEC, 100.0)
    assert q == pytest.approx(0.142, abs=1e-9)    # 100/700 = 0,142857 → 0,142 al paso 0,001
    assert bench.qty_for(idea(entry=70_000.0, sl=70_000.0), SPEC, 100.0) == 0.0
    assert bench.qty_for(i, SPEC, 0.05) == 0.0    # por debajo de la cantidad mínima


def test_every_policy_gets_the_same_entries_and_the_same_quantity():
    p = walk_path(200, seed=1)
    ideas = random_ideas(p, 12, seed=2, strategy="s")
    b = bench.run(ideas, [M0, M1], ctx(p, COSTED), RISK)
    assert b.policies == ("M0", "M1")
    for row in b.rows:
        qs = {t.qty for t in row.by_policy.values() if t is not None}
        assert len(qs) <= 1 and (not qs or qs.pop() == row.qty)
    for row in b.paired():
        a, c = row.by_policy["M0"], row.by_policy["M1"]
        assert a.id == c.id and a.t == c.t and a.side == c.side and a.risk_usd == c.risk_usd


def test_only_the_rows_closed_by_every_policy_are_paired():
    p = walk_path(200, seed=3)
    ideas = random_ideas(p, 20, seed=4, strategy="s")
    b = bench.run(ideas, [M0, M1], ctx(p, ZERO), RISK)
    assert len(b.paired()) <= len(b.rows)
    assert all(r.complete for r in b.paired())
    assert len(b.diffs("M1", "M0")) == len(b.paired())
    # lo que cada salida deja fuera queda contado por estado, nunca escondido
    assert set(b.dropped) == {"M0", "M1"}
    assert b.to_json()["paired"] == len(b.paired())


def test_duplicated_policy_ids_are_refused():
    p = walk_path(40, seed=5)
    with pytest.raises(ValueError, match="identificador repetido"):
        bench.run(random_ideas(p, 2, seed=6), [M1, ShadowExit()], ctx(p, ZERO), RISK)


def test_r_does_not_depend_on_the_fixed_risk_but_the_usdt_does():
    p = walk_path(200, seed=7)
    ideas = random_ideas(p, 10, seed=8, strategy="s")
    small = bench.run(ideas, [M0], ctx(p, COSTED), 100.0)
    big = bench.run(ideas, [M0], ctx(p, COSTED), 1000.0)
    a = {t.id: t for t in small.trades("M0")}
    for t in big.trades("M0"):
        if t.id in a:
            assert t.r == pytest.approx(a[t.id].r, abs=5e-3)   # el redondeo al paso mueve algo
            assert abs(t.pnl_usd) > abs(a[t.id].pnl_usd) * 5


def test_the_control_entries_are_separated_from_the_strategy_entries():
    p = walk_path(100, seed=9)
    mix = random_ideas(p, 6, seed=10) + random_ideas(p, 6, seed=11, strategy="consenso")
    assert len(bench.control_ideas(mix)) == 6
    assert len(bench.real_ideas(mix)) == 6
    assert all(i.strategy == bench.CONTROL_STRATEGY for i in bench.control_ideas(mix))


def _control(ep) -> dict[str, np.ndarray]:
    """R bruto (neto + costo) de cada salida sobre `PATHS` caminos independientes."""
    acc: dict[str, list] = {"M0": [], "M1": []}
    for s in range(PATHS):
        p = walk_path(BARS, seed=SEED + s)
        ideas = random_ideas(p, 1, seed=SEED + 10_000 + s)
        b = bench.run(ideas, [M0, M1], ctx(p, ep), RISK)
        for pid in acc:
            acc[pid] += b.trades(pid)
    return {k: np.array([t.r + t.cost_r for t in v], dtype=float) for k, v in acc.items()}


@pytest.mark.parametrize("pid", ["M0", "M1"])
def test_random_entries_are_not_profitable_gross_with_any_exit(pid: str):
    """Aceptación de T131: el control aleatorio da ≈ −costo, es decir, bruto ≈ 0."""
    g = _control(COSTED)[pid]
    assert len(g) > 150
    half = 1.96 * float(g.std(ddof=1)) / np.sqrt(len(g))
    lo, hi = float(g.mean()) - half, float(g.mean()) + half
    assert lo <= 0 <= hi, f"{pid}: bruto {g.mean():+.4f} IC [{lo:+.4f}, {hi:+.4f}] sin el 0"


@pytest.mark.parametrize("pid", ["M0", "M1"])
def test_without_costs_random_entries_have_zero_expectancy(pid: str):
    """Propiedad 7 de §5.2: paseo aleatorio sin costos ⇒ E[R] ≈ 0 (cientos de semillas)."""
    g = _control(ZERO)[pid]
    half = 1.96 * float(g.std(ddof=1)) / np.sqrt(len(g))
    assert abs(float(g.mean())) <= half, f"{pid}: E[R] {g.mean():+.4f} fuera de ±{half:.4f}"


def test_an_idea_that_nobody_can_trade_is_counted_not_silently_dropped():
    p = walk_path(60, seed=12)
    tiny = idea(entry=70_000.0, sl=69_999.0, tp=71_000.0, t=int(p.t[1]))   # cantidad < mínimo
    b = bench.run([tiny], [M0], ctx(p, ZERO), 0.0005)
    assert b.skipped_qty == 1 and not b.rows


def test_bench_trade_day_is_the_utc_day_of_the_decision():
    p = walk_path(60, seed=13)
    ideas = random_ideas(p, 3, seed=14, strategy="s")
    b = bench.run(ideas, [M0], ctx(p, ZERO), RISK)
    for t in b.trades("M0", paired_only=False):
        assert t.day == t.t // 86_400_000 >= T0 // 86_400_000
