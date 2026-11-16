"""Escalafón de la cantera (T170): las pruebas que pide `PLAN/T170.md`, con los umbrales publicados.

Datos sintéticos, sin red ni disco: cada operación lleva su d (R − media de los gemelos) y su P&L.
El control aleatorio usa el modelo de los gemelos (`calibrate.null_d`): el lado real es un lado más
al azar frente a 200 gemelos.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.nursery import calibrate, evalue
from eim.nursery.ladder import BAJA, CANTERA, GUARDERIA, PROMESA, Member, evaluate
from eim.nursery.ladder_stats import DAY_MS, H_MS, AccountData, Closed
from eim.nursery.prereg import load_prereg

PR = load_prereg()
ALTA = 1_800_000_000_000
END = ALTA + PR.ladder.deadline_days * DAY_MS
MID = ALTA + PR.ladder.reviews_days[3] * DAY_MS     # día 121: antes de la fecha límite
RISK_USD = 100.0                       # 1 % de 10 000


def _rules(ids, cap=99.0):
    dd = PR.ladder.drawdown.model_copy(update={"caps_pct": {i: cap for i in ids}})
    return PR.ladder.model_copy(update={"drawdown": dd})


def _member(pid, sibling=None, n_params=1, agent="x"):
    return Member(pid, agent, "1h", n_params, "intradia", True, "tendencia", sibling, None)


def _account(d, pnl=None, days=PR.ladder.deadline_days, hold_h=2.0):
    """Operaciones repartidas por igual en la fase, una tras otra."""
    d = np.asarray(d, float)
    n = len(d)
    step = days * DAY_MS // max(n, 1)
    pnl = RISK_USD * d if pnl is None else np.asarray(pnl, float)
    cs = []
    for i in range(n):
        f = ALTA + i * step + H_MS
        cs.append(Closed(f - H_MS, f, f + int(hold_h * H_MS), float(d[i]), float(pnl[i]),
                         0.1, float(d[i])))
    return AccountData(tuple(cs), tuple((c.fill_t, c.exit_t) for c in cs))


def _eval(members, accounts, m, t=END, rules=None, **kw):
    rules = rules or _rules([mb.id for mb in members])
    return evaluate(members, accounts, rules, ALTA, t, m, 10_000.0, **kw)


def test_random_control_reaches_promise_at_most_alpha_over_1000_seeds():
    """rec. 5: un control al azar llega a Promesa con frecuencia ≤ α (aquí m = 1, el caso más
    favorable al azar: e-BH pide e ≥ 1/q); «nunca» sería falso o indicaría potencia nula."""
    q, hits, seeds = PR.ladder.promise.q, 0, 1000
    rng = np.random.default_rng(170)
    mb = _member("control")
    rules = _rules(["control"])
    for _ in range(seeds):
        acc = _account(calibrate.null_d(rng, (300,)))
        st = evaluate([mb], {"control": acc}, rules, ALTA, END, 1, 10_000.0)["control"]
        hits += st.frozen_e is not None
    assert hits / seeds <= q
    assert hits > 0, "con m = 1 el azar tiene que poder colarse alguna vez"


def test_family_of_random_controls_stays_under_q():
    fp = calibrate.false_promises({f"c{i}": 200 for i in range(29)}, PR.ladder, PR.m, 1000, 7)
    assert fp["p_at_least_one"] <= PR.ladder.promise.q


def test_large_edge_reaches_promise():
    rng = np.random.default_rng(1)
    st = _eval([_member("bueno")], {"bueno": _account(rng.normal(0.6, 1.0, 300))}, PR.m, t=MID)
    assert st["bueno"].stage == PROMESA
    assert {c["id"]: c["ok"] for c in st["bueno"].criteria}["e_bh"] is True


def test_one_lucky_trade_fails_consistency():
    rng = np.random.default_rng(2)
    d = rng.normal(0.6, 1.0, 300)
    pnl = np.full(300, 1.0)
    pnl[150] = 5_000.0                       # una sola operación explica casi todo el beneficio
    st = _eval([_member("suerte")], {"suerte": _account(d, pnl)}, PR.m, t=MID)["suerte"]
    crit = {c["id"]: c for c in st.criteria}
    assert st.stage == CANTERA and crit["consistencia"]["ok"] is False
    assert crit["consistencia"]["value"] > PR.ladder.promise.max_trade_share


def test_complex_that_ties_its_simple_sibling_does_not_ascend():
    rng = np.random.default_rng(3)
    base, cplx = _member("base"), _member("complejo", sibling="base", n_params=2)
    acc = {"base": _account(rng.normal(0.6, 1.0, 300)),
           "complejo": _account(rng.normal(0.6, 1.0, 300))}
    st = _eval([base, cplx], acc, PR.m, t=MID)
    assert st["base"].stage == PROMESA
    crit = {c["id"]: c["ok"] for c in st["complejo"].criteria}
    assert st["complejo"].stage == CANTERA and crit["hermano_simple"] is False


def _n_between(c, lo, hi):
    """Operaciones con d constante c cuyo e-valor queda en [lo, hi)."""
    for n in range(30, 400):
        e = evalue.promise_evalue([c] * n, PR.ladder.primary.clip_r, PR.ladder.primary.lambdas)
        if lo <= e < hi:
            return n
    raise AssertionError("sin n en el intervalo")


def test_a_dropped_prospect_keeps_counting_in_the_family():
    q = PR.ladder.promise.q
    n = _n_between(0.3, 1 / q, 2 / q)        # pasa e-BH con m = 1, no con m = 2
    good = _account([0.3] * n, days=25)
    bad = _account([-0.5] * 40, days=25)
    a, b = _member("a"), _member("b")
    t = ALTA + PR.ladder.reviews_days[0] * DAY_MS
    both = _eval([a, b], {"a": bad, "b": good}, 2, t=t)
    assert both["a"].stage == BAJA and both["a"].exit["reason"] == "futilidad"
    assert both["b"].stage == CANTERA, "la baja de «a» no reduce m"
    alone = _eval([b], {"b": good}, 1, t=t)
    assert alone["b"].stage == PROMESA
    with pytest.raises(ValueError, match="familia"):
        _eval([a, b], {"a": bad, "b": good}, 1, t=t)


def test_stage_ignores_trades_closed_after_t():
    rng = np.random.default_rng(4)
    acc = _account(rng.normal(0.6, 1.0, 300))
    t = ALTA + PR.ladder.reviews_days[2] * DAY_MS
    cut = AccountData(tuple(c for c in acc.closed if c.exit_t <= t),
                      tuple(f for f in acc.fills if f[0] <= t))
    future = [Closed(t + DAY_MS, t + DAY_MS, t + 2 * DAY_MS, -3.0, -1e6)]
    poisoned = AccountData(cut.closed + tuple(future), cut.fills + ((t + DAY_MS, t + 2 * DAY_MS),))
    a = _eval([_member("p")], {"p": cut}, PR.m, t=t)["p"]
    b = _eval([_member("p")], {"p": poisoned}, PR.m, t=t)["p"]
    assert a.to_json() == b.to_json()


def test_nursery_until_first_review_and_inactivity_skips_closed_gate_days():
    st = _eval([_member("q")], {}, PR.m, t=ALTA + DAY_MS)["q"]
    assert st.stage == GUARDERIA and st.reviews == 0
    t = ALTA + PR.ladder.reviews_days[1] * DAY_MS
    idle = _eval([_member("q")], {}, PR.m, t=t)["q"]
    assert idle.stage == BAJA and idle.exit["reason"] == "inactividad"
    spans = {"1h": [(ALTA + 5 * DAY_MS, t)]}     # la puerta cerró el marco casi todo el tiempo
    kept = _eval([_member("q")], {}, PR.m, t=t, closed_spans=spans)["q"]
    assert kept.stage != BAJA or kept.exit["reason"] != "inactividad"


def test_deadline_drops_everyone_who_is_not_a_promise():
    rng = np.random.default_rng(5)
    st = _eval([_member("tibio")], {"tibio": _account(rng.normal(0.0, 1.0, 120))}, PR.m)
    assert st["tibio"].stage == BAJA and st["tibio"].exit["reason"] in (
        "fecha_limite", "futilidad")


def test_drawdown_over_the_calibrated_cap_drops():
    d = [-1.0] * 60
    st = _eval([_member("dd")], {"dd": _account(d, pnl=[-100.0] * 60)}, PR.m,
               rules=_rules(["dd"], cap=20.0))["dd"]
    assert st.stage == BAJA and st.exit["reason"] == "drawdown"


def test_a_promise_that_drops_still_counts_as_rejected_for_the_others():
    from eim.nursery.ladder import Standing, _review
    q = PR.ladder.promise.q
    n = _n_between(0.3, 2 / (2 * q), 2 / q)  # pasa e-BH con 2 rechazos a la vez (m = 2), no solo
    a, b = _member("a"), _member("b")
    rules = _rules(["a", "b"])
    good = _account([0.3] * n, days=25)
    stand = {"a": Standing("a", stage=BAJA, since_ms=ALTA, band="intradia", frozen_e=1e6,
                           exit={"reason": "drawdown", "at_ms": ALTA}),
             "b": Standing("b", stage=CANTERA, since_ms=ALTA, band="intradia")}
    t = ALTA + PR.ladder.reviews_days[0] * DAY_MS
    _review([a, b], {"b": good}, {"b": good}, {}, stand, rules, ALTA, t, 2, 10_000.0, False)
    assert stand["b"].stage == PROMESA
