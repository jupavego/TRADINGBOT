"""T136 (4): freno de drawdown GRADUAL y límite de CVaR por perfil."""

from __future__ import annotations

import pytest

from eim.paper import risk_budget as rb
from eim.paper.book import run_profile
from eim.paper.caps import CVAR_WINDOW, Brake, CapParams, cvar95_r, cvar_scale, dd_scale
from eim.paper.feedback import Learner
from eim.paper.params import PROFILES
from tests.paper.test_feedback_book import MOD, closed

STEPS = ((0.03, 0.5), (0.05, 0.25), (0.08, 0.0))


def test_off_by_default_everywhere():
    assert CapParams().dd_steps == ()
    assert CapParams().cvar_limit_r is None
    assert all(p.caps.dd_steps == () for p in PROFILES)
    assert all(p.caps.cvar_limit_r is None for p in PROFILES)
    assert dd_scale(CapParams(), 10_000, 9_000) == (1.0, "")
    assert cvar_scale(CapParams(), -9.0, 500) == (1.0, "")


@pytest.mark.parametrize(("equity", "scale"), [
    (10_000, 1.0), (9_900, 1.0), (9_700, 0.5), (9_600, 0.5),
    (9_500, 0.25), (9_300, 0.25), (9_150, 0.0), (8_000, 0.0)])
def test_the_deepest_step_reached_is_the_one_that_applies(equity, scale):
    caps = CapParams(dd_steps=STEPS)
    got, why = dd_scale(caps, 10_000, equity)
    assert got == scale
    assert bool(why) is (scale < 1.0)


def test_steps_do_not_need_to_come_sorted():
    a = dd_scale(CapParams(dd_steps=STEPS), 10_000, 9_400)
    b = dd_scale(CapParams(dd_steps=tuple(reversed(STEPS))), 10_000, 9_400)
    assert a == b


def test_above_the_peak_there_is_no_cut():
    assert dd_scale(CapParams(dd_steps=STEPS), 10_000, 11_000) == (1.0, "")
    assert dd_scale(CapParams(dd_steps=STEPS), 0.0, 9_000) == (1.0, "")


def test_gradual_recovers_without_waiting_hours():
    """Es la diferencia con el freno todo o nada: no hay pausa, hay tamaño menor."""
    caps = CapParams(dd_steps=STEPS)
    assert dd_scale(caps, 10_000, 9_150)[0] == 0.0
    assert dd_scale(caps, 10_000, 9_900)[0] == 1.0


def test_cvar95_is_the_mean_of_the_left_tail():
    assert cvar95_r([]) == 0.0
    rs = [-5.0] * 5 + [0.1] * 95
    assert cvar95_r(rs) == pytest.approx(-5.0)           # el 5 % peor de 100 son 5 operaciones
    # es la MEDIA de la cola, no el cuantil: una sola pérdida grande se reparte entre las 5
    assert cvar95_r([-5.0] + [0.1] * 99) == pytest.approx((-5.0 + 0.4) / 5)
    assert cvar95_r([-1.0, 1.0]) == pytest.approx(-1.0)


def test_cvar_limit_cuts_only_with_sample_and_when_it_is_worse():
    caps = CapParams(cvar_limit_r=-1.35, cvar_min_n=30, cvar_cut=0.5)
    assert cvar_scale(caps, -1.50, 29) == (1.0, "")       # sin muestra no se recorta
    assert cvar_scale(caps, -1.20, 100) == (1.0, "")      # mejor que el límite: no se recorta
    got, why = cvar_scale(caps, -1.50, 100)
    assert got == 0.5 and "CVaR" in why


def test_brake_keeps_a_bounded_tail_and_recomputes_the_cvar_on_close():
    caps = CapParams()
    b = Brake()
    for i in range(CVAR_WINDOW + 50):
        b.closed(caps, 10_000.0, 10_000.0, i, -1.0 if i % 20 == 0 else 0.1)
    assert len(b.rs) == CVAR_WINDOW
    assert b.cvar_r == pytest.approx(cvar95_r(tuple(b.rs)))
    assert b.cvar_r < 0


def test_close_without_r_keeps_working_like_before():
    b = Brake()
    assert b.closed(CapParams(dd_brake=0.05), 9_000.0, 10_000.0, 1_000) is not None
    assert len(b.rs) == 0 and b.cvar_r == 0.0


def test_scale_multiplies_both_cuts_and_reports_the_stronger_one():
    caps = CapParams(dd_steps=STEPS, cvar_limit_r=-1.35, cvar_min_n=2, cvar_cut=0.5)
    b = Brake(peak=10_000.0)
    b.rs.extend([-2.0, -2.0, 0.1])
    b.cvar_r = cvar95_r(tuple(b.rs))
    got, why = b.scale(caps, 9_700.0)                    # 3 % → ×0,5, y CVaR → ×0,5
    assert got == pytest.approx(0.25)
    assert "drawdown" in why or "CVaR" in why


def test_scale_is_neutral_with_everything_off():
    assert Brake(peak=10_000.0).scale(CapParams(), 9_000.0) == (1.0, "")


def test_policy_cuts_the_size_by_the_gradual_brake():
    """Integración: el recorte llega al tamaño de verdad, y con tramo 0 rechaza con su código."""
    outs = [closed(-1.0, k, strategy=f"s{k}") for k in range(4)]
    outs += [closed(1.0, 40, strategy="s40")]
    base = run_profile(MOD, outs, Learner(outs), 0.005)
    # tramos a la escala de este fixture: con el peso de «en observación» cada pérdida es
    # ≈ 0,27 % del capital, así que los tramos van en décimas de punto
    grad = MOD.model_copy(update={"caps": CapParams(dd_steps=((0.002, 0.5), (0.005, 0.0)))})
    st = run_profile(grad, outs, Learner(outs), 0.005)
    qty_of = {x["id"]: x["qty"] for x in base.trades}
    cut = [t for t in st.trades if t["qty"] < qty_of[t["id"]]]
    assert cut, "tras la primera pérdida el freno gradual ya debería recortar el tamaño"
    # el primero recortado es comparable al dedillo: hasta ahí las dos corridas van con el mismo
    # capital. Luego ya no, porque la frenada hace perder menos y el capital se separa.
    first = min(cut, key=lambda x: x["t"])
    assert first["qty"] == pytest.approx(qty_of[first["id"]] * 0.5, rel=1e-6)
    assert all(t["qty"] <= qty_of[t["id"]] for t in st.trades)
    assert any("freno gradual" in e["text"] for e in st.events if e["cat"] == "rechazada")
    assert st.rejected.get("freno_gradual", 0) >= 1


def test_policy_sizing_with_costs_included_risks_exactly_what_it_declares():
    """Integración de T136 (1): el riesgo realizado al SL pasa a ser el declarado."""
    outs = [closed(-1.0, 0, strategy="s0")]
    sin = run_profile(MOD, outs, Learner(outs), 0.005)
    con = run_profile(MOD.model_copy(update={"risk_includes_costs": True}), outs,
                      Learner(outs), 0.005)
    a, b = sin.trades[0], con.trades[0]
    cost_r = rb.cost_r(a["fill"], a["sl"], MOD.est_cost_frac)
    assert b["qty"] == pytest.approx(a["qty"] / (1 + cost_r))

    def loss(t):
        """Lo que arriesga hasta el SL, costos incluidos."""
        return t["qty"] * (abs(t["fill"] - t["sl"])
                           + rb.cost_per_unit(t["fill"], MOD.est_cost_frac))

    # la propiedad, sin depender del peso de la retroalimentación: lo que se pierde al SL es
    # exactamente el riesgo informado cuando los costos van dentro, y un 16 % más cuando no
    assert loss(b) == pytest.approx(b["risk_usd"], rel=1e-6)
    assert loss(a) == pytest.approx(a["risk_usd"] * (1 + cost_r), rel=1e-6)
    assert loss(a) > a["risk_usd"]
