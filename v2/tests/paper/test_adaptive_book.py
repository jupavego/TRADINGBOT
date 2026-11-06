"""T135 — La salida adaptativa en el libro: apagada para todos y, encendida, con sus reglas.

Costos cero para que las cuentas se lean a mano. Se comprueba: que ningún perfil la usa ni cambia su
huella; que el libro da lo mismo que el motor que midió T134; que solo cierra lo pre-registrado; que
una señal contraria no toca la posición; y que cada operación dice su fase, motivo y versión.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import numpy as np
import pytest

from eim.backtest.params import ZERO_COSTS
from eim.core.authority import params_fingerprint
from eim.paper.ab_gate import gate_trades
from eim.paper.adaptive import (
    audit_adaptive,
    build_policy,
    close_violation,
    decorate,
    exit_identity,
    exit_version,
    motive,
    open_adaptive,
    policies_for,
    simulate_adaptive,
)
from eim.paper.adaptive_params import AdaptiveParams
from eim.paper.book import ProfileState, Slot, _close, run_profile
from eim.paper.engine import Outcome, Path, simulate
from eim.paper.exits.policy import ExitContext
from eim.paper.feedback import Learner
from eim.paper.ladder_book import LadderRisk, LadderSim
from eim.paper.ladder_floor import Guard
from eim.paper.ladder_metrics import profile_metrics
from eim.paper.params import PROFILES, ExecParams, check_profiles, spec_for
from eim.paper.policy import EXIT_OF
from eim.paper.summary import profile_summary
from eim.risk.authority import EXIT_RULES, SOURCES, verify_route
from tests.paper.helpers import M15, T0, idea
from tests.paper.test_ladder_stop_only_book import btc, mirror

E = 70_000.0
EP = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
BASE = {p.id: p for p in PROFILES}["moderado"]
# Una vela tranquila para el σ de arranque, sube mucho y retrocede hasta el stop movido
RUN = ([(E, E + 50, E - 20, E + 30)] * 3
       + [(E + 40, E + 3000, E + 30, E + 2990)]
       + [(E + 2990, E + 3000, E + 2980, E + 2990)] * 4
       + [(E + 2990, E + 2995, E + 200, E + 300)])


def adaptive_profile(policy: str = "M2", **kw):
    ap = AdaptiveParams(policy=policy, floor_n=0.0, **kw)
    return BASE.model_copy(update={"exit_mode": "adaptativo", "ladder": None, "adaptive": ap})


def sigma_flat(n: int, value: float = 100.0) -> np.ndarray:
    return np.full(n, value)


def sim_for(p, rows, side: int = 1, sigma: float | None = 100.0) -> tuple[LadderSim, Path]:
    path = mirror(rows, side)
    pol = build_policy(p, path)
    if sigma is not None:           # σ fija para leer el stop a mano: extremo − k·σ
        pol = replace(pol, feats=replace(pol.feats, sigma_abs=sigma_flat(len(path.t), sigma)))
    return LadderSim(path, EP, exits={p.id: pol}), path


def run(p, ideas, rows, side: int = 1):
    sim, path = sim_for(p, rows, side)
    shadows = [simulate(i, path, EP) for i in ideas]
    return run_profile(p, shadows, Learner(shadows), 0.004, sim), sim


# --- apagada: nada de lo vigente cambia ------------------------------------------------------


def test_no_profile_uses_it_and_the_dump_does_not_mention_it():
    assert all(p.exit_mode != "adaptativo" and p.adaptive is None for p in PROFILES)
    for p in PROFILES:
        assert "adaptive" not in p.model_dump()
        assert '"adaptive"' not in p.model_dump_json()


def test_serializer_keeps_the_fingerprint_of_a_profile_identical():
    """La huella de hoy es la del volcado sin `adaptive`: la versión del perfil no se mueve."""
    for p in PROFILES:
        got = p.model_dump_json()
        assert params_fingerprint(p) == hashlib.sha256(got.encode("utf-8")).hexdigest()[:12]
        assert list(p.model_dump())[-2:] == ["feedback", "caps"]


def test_an_adaptive_profile_does_carry_it_and_round_trips():
    p = adaptive_profile()
    assert p.model_dump()["adaptive"]["policy"] == "M2"
    assert params_fingerprint(p) != params_fingerprint(BASE)
    assert type(p).model_validate(p.model_dump()).adaptive == p.adaptive


def test_mode_and_policy_go_together():
    with pytest.raises(ValueError, match="van juntos"):
        BASE.model_validate({**BASE.model_dump(), "exit_mode": "adaptativo", "ladder": None})
    with pytest.raises(ValueError, match="van juntos"):
        BASE.model_validate({**BASE.model_dump(), "adaptive": {"policy": "M2"}})
    with pytest.raises(ValueError, match="una sola salida"):
        BASE.model_validate({**BASE.model_dump(), "exit_mode": "adaptativo",
                             "adaptive": {"policy": "M2"}})


@pytest.mark.parametrize("name", ["S1", "M8", "M0", "M1"])
def test_policies_that_move_the_initial_stop_are_not_allowed(name):
    with pytest.raises(ValueError):
        AdaptiveParams(policy=name)


def test_m6_needs_its_barrier():
    with pytest.raises(ValueError, match="M6 exige"):
        AdaptiveParams(policy="M6")


def test_unknown_volatility_estimator_fails_when_building_the_profile():
    with pytest.raises(ValueError, match="estimador de volatilidad"):
        AdaptiveParams(policy="M2", sigma="atr_14")
    assert AdaptiveParams(policy="M2", sigma="harrv_1m").sigma == "harrv_1m"


def test_startup_check_covers_adaptive_profiles():
    p = adaptive_profile().model_copy(update={"symbols": None})
    check_profiles((p,), ("BTCUSDT",))
    with pytest.raises(ValueError, match=p.id):
        check_profiles((p,), ("NOEXISTEUSDT",))


def test_learned_weight_has_the_same_cap_as_the_ladder():
    """Una racha buena no infla el tamaño más que en la escalera: mezclaría salida y tamaño."""
    p = adaptive_profile(max_weight=1.1)
    risk = LadderRisk(r_by_sid={"s": [3.0] * 200})
    plain = p.model_copy(update={"adaptive": None, "exit_mode": "tp"})
    assert risk.strategy("s", plain).weight > 1.1
    assert risk.strategy("s", p).weight == pytest.approx(1.1)


def test_without_adaptive_profiles_nothing_is_built_or_read():
    def boom():
        raise AssertionError("no se debe leer el marco mayor sin un perfil M7")
    assert policies_for(PROFILES, "BTCUSDT", mirror(RUN, 1), None, boom) == {}


# --- ruta por la autoridad -------------------------------------------------------------------


def test_route_is_registered_in_the_single_gate():
    assert EXIT_OF["adaptativo"] == "adaptive_stop"
    assert "adaptive_stop" in SOURCES["paper.strategies"].exit_modes
    assert "señal" not in " ".join(EXIT_RULES["adaptive_stop"]).lower()


def test_book_vetoes_it_if_the_route_is_withdrawn(monkeypatch):
    import eim.paper.policy as pol
    monkeypatch.setattr(pol, "route_reason", lambda *a: "modo no registrado")
    st, _ = run(adaptive_profile(), [btc()], RUN)
    assert st.trades == [] and st.rejected.get("puerta") == 1


def test_live_decision_is_recorded_with_its_exit_mode_and_a_valid_route():
    p = adaptive_profile()
    st, _ = run(p, [replace(btc(), origin="vivo")], RUN)
    (d,) = st.decisions
    rec = d.as_record(p)
    assert rec.approved and rec.exit_mode == "adaptive_stop" and rec.tp == ()
    verify_route(rec.proposal, rec.authority, rec.exit_mode)


def test_the_flip_replica_does_not_borrow_the_floor_of_the_real_trade():
    """La réplica de V3 no ocurrió: con el suelo de la real saldría «inconsistente», como la
    escalera, que tampoco se lo pasa."""
    p = adaptive_profile()
    i = btc()
    sim, path = sim_for(p, RUN)
    hold = replace(sim, guards={(p.id, i.id): Guard(None, "congelada")})
    assert simulate_adaptive(p, hold, i, 0.01).ladder["inconsistent"] == "congelada"
    assert simulate_adaptive(p, hold, i, 0.01, guarded=False).ladder["inconsistent"] is None
    trades = [{"id": i.id, "qty": 0.01, "exit_t": T0 + M15, "r": 0.5, "risk_usd": 14.0,
               "fees": 0.0, "slip": 0.0, "funding": 0.0, "notional": 700.0}]
    (got,) = gate_trades(trades, {i.id: simulate(i, path, EP)}, hold, p)
    assert got.r == 0.5


def test_metrics_of_the_exit_read_adaptive_trades():
    """El informe de calidad de salida (T130) y las métricas leen las mismas claves."""
    st, _ = run(adaptive_profile(), [btc()], RUN)
    m = profile_metrics(st.trades, [], 0.0, None)
    assert m["n"] == 1 and m["inconsistent"] == 0


def test_it_needs_the_price_path_and_its_policy():
    p = adaptive_profile()
    with pytest.raises(ValueError, match="necesita el camino"):
        run_profile(p, [], Learner([]), 0.004, None)
    with pytest.raises(ValueError, match="no tiene política"):
        open_adaptive(p, LadderSim(mirror(RUN, 1), EP), btc(), 0.01)


# --- el libro y el motor dicen lo mismo ------------------------------------------------------


@pytest.mark.parametrize("side", [1, -1])
def test_book_matches_the_engine_that_t134_measured(side):
    p = adaptive_profile(k=3.0)
    i = btc(side)
    st, sim = run(p, [i], RUN, side)
    (t,) = st.trades
    raw = sim.exits[p.id].simulate(i, ExitContext(sim.path, EP, spec_for("BTCUSDT")), t["qty"])
    assert (t["reason"], t["exit"], t["exit_t"], t["fill"]) == (
        raw.reason, raw.exit, raw.exit_t, raw.fill)
    assert t["reason"] == "SLD" and t["tp"] is None and st.violations == []
    # el extremo llega a +3 000 y el stop queda en extremo − 3·σ
    assert t["ladder"]["stop"] == pytest.approx(E + side * (3000 - 300), abs=1)


def test_every_trade_says_its_phase_motive_source_and_version():
    p = adaptive_profile(k=3.0)
    st, _ = run(p, [btc()], RUN)
    (t,) = st.trades
    e = t["ladder"]["exit"]
    assert (e["mode"], e["policy"], e["version"]) == ("adaptativo", "M2", exit_version(p))
    assert e["phase"] == "arrastre" and "3·σ" in e["motive"]
    assert e["source"] == f"M2@{exit_version(p)}" and e["features"] == "v1"
    for h in t["ladder"]["stop_history"]:
        assert {"phase", "motive", "source", "version", "features", "level"} <= set(h)


def test_learning_comes_from_its_own_closes_not_from_the_shadow():
    st, _ = run(adaptive_profile(), [btc()], RUN)
    assert st.lrisk.r_by_sid[btc().sid] == [st.trades[0]["r"]]


def test_contrary_signal_only_informs():
    p = adaptive_profile()
    later = replace(idea(side=-1, entry=E + 2990, sl=E + 4390, tp=E + 790, t=T0 + 5 * M15,
                         strategy="otra", syn_bias=-0.5), symbol="BTCUSDT", htf=-1)
    st, _ = run(p, [btc(), later], RUN)
    first = next(t for t in st.trades if t["side"] == 1)
    assert first["reason"] == "SLD"           # no la cerró la señal contraria
    assert st.contrary >= 1


def test_summary_exposes_the_block_with_source_and_coverage():
    p = adaptive_profile()
    st, _ = run(p, [btc()], RUN)
    d = profile_summary(st, Learner([]), [], T0 + 100 * M15, 0.004)
    assert d["adaptive"]["policy"] == "M2" and d["adaptive"]["version"] == exit_version(p)
    assert d["adaptive"]["params"] == exit_identity(p)["params"]
    assert d["adaptive"]["feature_info"]["version"] == "v1"
    assert set(d["adaptive"]["feature_info"]["coverage"]) >= {"sigma_abs", "htf_dir"}
    assert d["adaptive"]["closes"] == {"SLD": 1}
    assert "ladder" not in d and d["learning"] == "cierres propios (salida adaptativa)"
    assert "adaptive" not in profile_summary(run_profile(
        BASE.model_copy(update={"exit_mode": "tp"}), [], Learner([]), 0.004),
        Learner([]), [], T0, 0.004)


def test_open_position_reports_float_and_stop_estimate():
    p = adaptive_profile()
    sim, _ = sim_for(p, RUN[:6])
    q, o = open_adaptive(p, sim, btc(), 0.01)
    assert q == pytest.approx(0.01) and o.status == "ABIERTA"
    lad = o.ladder
    assert lad["float_usd"] == pytest.approx(0.01 * (o.mark - o.fill))
    assert lad["stop_est_usd"] == pytest.approx(0.01 * (lad["stop"] - o.fill))
    assert lad["exit"]["phase"] == "arrastre" and lad["active"] is True


def test_quantity_below_the_minimum_is_rejected_not_rounded_up():
    p = adaptive_profile()
    sim, _ = sim_for(p, RUN)
    q, o = open_adaptive(p, sim, btc(), spec_for("BTCUSDT").min_qty / 2)
    assert o.status == "RECHAZADA" and o.reason == "CANTIDAD" and q == 0.0


# --- solo cierra lo pre-registrado -----------------------------------------------------------


@pytest.mark.parametrize(("policy", "kw", "own", "other"), [
    ("M6", {"bars": 3}, "TIEMPO", "HTF"),
    ("M7", {}, "HTF", "TIEMPO"),
])
def test_each_policy_only_gets_its_own_extra_close(policy, kw, own, other):
    p = adaptive_profile(policy, **kw)
    assert close_violation(p, own) is None and close_violation(p, "SLD") is None
    assert close_violation(p, other)


@pytest.mark.parametrize("reason", ["TP", "TIEMPO", "HTF", "AGENTE", "MANUAL", "RAROS"])
def test_a_trailing_policy_cannot_be_closed_by_anything_else(reason):
    assert close_violation(adaptive_profile(), reason)


def test_book_refuses_a_close_outside_the_rules_and_keeps_the_position():
    """Un cierre por tiempo en M2 no se ejecuta: se registra y la posición sigue abierta."""
    p = adaptive_profile()
    i = btc()
    o = Outcome(i, "CERRADA", "TIEMPO", T0, E, T0 + M15, E,
                ladder={"stop_history": [], "stop": i.sl})
    st = ProfileState(p=p, equity=p.initial_equity)
    st.slots[i.id] = Slot(o, 0.01, 5, 100.0, 1.0, 50.0, filled=True)
    _close(st, o)
    assert i.id in st.slots and st.trades == []
    assert st.violations[0]["executed"] is False


def test_time_barrier_closes_and_counts_as_time():
    st, _ = run(adaptive_profile("M6", bars=2), [btc()], RUN)
    (t,) = st.trades
    assert t["reason"] == "TIEMPO" and st.violations == []
    assert "cierra a las 2 velas" in t["ladder"]["exit"]["motive"]


def test_audit_catches_a_stop_that_went_back():
    p = adaptive_profile()
    i = btc()
    bad = Outcome(i, "ABIERTA", "", T0, E, ladder={
        "stop": E, "incident": "", "stop_history": [{"stop": E - 100}, {"stop": E - 500}]})
    assert any("trinquete" in x for x in audit_adaptive(bad, p))


def test_audit_catches_a_stop_close_better_than_the_stop():
    p = adaptive_profile()
    i = btc()
    bad = Outcome(i, "CERRADA", "SL", T0, E, T0 + M15, E + 900,
                  ladder={"stop": i.sl, "incident": "", "stop_history": []})
    assert any("mejor que el SL" in x for x in audit_adaptive(bad, p))


# --- versión y motivo ------------------------------------------------------------------------


def test_version_depends_only_on_what_the_policy_uses():
    assert exit_version(adaptive_profile(k=3.0)) != exit_version(adaptive_profile(k=4.0))
    assert exit_version(adaptive_profile(survival_r=0.9)) == exit_version(adaptive_profile())
    m7 = exit_version(adaptive_profile("M7", k=4.0))
    assert m7 == exit_version(adaptive_profile("M7"))


def test_motive_explains_each_situation():
    p = adaptive_profile("M5", a_r=1.0, b_r=0.1)
    assert motive(p, []) == "SL inicial de la idea"
    assert "BE+" in motive(p, [{"source": "x", "phase": "equilibrio_mas"}])
    assert "extremo" in motive(p, [{"source": "x", "phase": "arrastre"}])
    assert "suelo recuperado" in motive(p, [{"source": "recuperado"}])
    m3 = adaptive_profile("M3", swing_bars=3)
    assert "swing confirmado de 3" in motive(m3, [{"source": "x", "phase": "arrastre"}])


def test_decorate_leaves_rejected_outcomes_alone():
    o = Outcome(btc(), "RECHAZADA", "GEOMETRIA")
    assert decorate(o, adaptive_profile(), EP) is o


def test_no_sigma_means_the_stop_does_not_tighten():
    """Sin σ (arranque del estimador) M2 no propone nada: la falta de datos no aprieta."""
    p = adaptive_profile()
    sim, _ = sim_for(p, RUN, sigma=float("nan"))
    _, o = open_adaptive(p, sim, btc(), 0.01)
    assert o.ladder["stop_history"] == [] and o.ladder["exit"]["source"] == "inicial"
    assert o.ladder["exit"]["motive"] == "SL inicial de la idea"
