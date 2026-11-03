"""T131 — estrés de costos (E4a): ×1,5 y ×2 en el deslizamiento de los stops, y nada más.

Lo que hay que demostrar es que el estrés toca el costo que distingue a una salida de otra (el
deslizamiento de las salidas a mercado) y deja intactos la entrada y las comisiones: si tocara la
entrada, el estrés castigaría por igual a todas las salidas y no mediría nada.
"""

from __future__ import annotations

import pytest

from eim.paper.exits import bench
from eim.paper.exits.costs import label, stressed
from tests.paper.exits.helpers import COSTED, M0, M1, ctx, random_ideas, walk_path


def test_the_base_factor_returns_the_very_same_params():
    assert stressed(COSTED, 1.0) is COSTED
    assert label(1.0) == "costo base" and "×1,5" in label(1.5).replace("1.5", "1,5")


def test_only_the_exit_slippage_is_multiplied():
    s = stressed(COSTED, 2.0)
    c, b = s.costs, COSTED.costs
    assert c.slip_base_bps == pytest.approx(b.slip_base_bps * 2)
    assert c.slip_vol_k == pytest.approx(b.slip_vol_k * 2)
    assert c.slip_cap_bps == pytest.approx(b.slip_cap_bps * 2)
    assert c.slip_entry_base_bps == b.slip_entry_base_bps     # la entrada no se toca
    assert c.slip_entry_vol_k == b.slip_entry_vol_k
    assert (c.taker_fee, c.maker_fee) == (b.taker_fee, b.maker_fee)   # ni las comisiones
    assert s.be_trigger_r == COSTED.be_trigger_r              # ni la mecánica de la salida


def test_making_costs_cheaper_is_refused():
    with pytest.raises(ValueError, match="nunca abarata"):
        stressed(COSTED, 0.9)


@pytest.mark.parametrize("pol", [M0, M1])
def test_the_stressed_bench_never_pays_less_than_the_base(pol):
    """Mismo camino, mismas entradas: con el estrés el costo medio en R sube o se queda igual."""
    p = walk_path(400, seed=31)
    ideas = random_ideas(p, 25, seed=32, strategy="s")
    out = {}
    for f in (1.0, 1.5, 2.0):
        b = bench.run(ideas, [pol], ctx(p, stressed(COSTED, f)), 100.0)
        ts = b.trades(pol.id)
        out[f] = sum(t.cost_r for t in ts) / len(ts)
    assert out[1.0] <= out[1.5] <= out[2.0]
    assert out[2.0] > out[1.0]
