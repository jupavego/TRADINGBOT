"""Puntuación de bots (T59): puerta de T49 aplicada a posturas, estados y aporte marginal."""

from __future__ import annotations

import pytest

from eim.bots.concept import DESHABILITADO, INFORMA, RECHAZADO, VOTA
from eim.bots.marginal import Marginal
from eim.bots.scorecard import score
from eim.bots.shadow import ideas_of, identities, shadow_trades
from tests.bots.score_helpers import (
    CRIT,
    SYMBOL,
    Market,
    card,
    noise_rows,
    oracle_rows,
    version,
)

BOT = "hummingbot-directional"
GOOD = Marginal(True, 0.25, "aporta (prueba)", 0.5)


@pytest.fixture(scope="module")
def mkt() -> Market:
    return Market()


def run(m, rows, cards=None, marginals=None, asof=None):
    return score(rows, m.c1h, m.path, SYMBOL, CRIT, cards or {BOT: card()}, asof or m.end,
                 m.regime_at, marginals)


def only(out: dict) -> dict:
    return out["bots"][0]


@pytest.fixture(scope="module")
def oracle(mkt):
    rows = oracle_rows(mkt)
    return rows, run(mkt, rows, marginals={"hummingbot-directional:s1@1h@v1": GOOD})


def test_bot_with_edge_validated_and_votes(oracle):
    b = only(oracle[1])
    assert b["verdict"]["verdict"] == "VALIDADA", b["verdict"]["reason"]
    assert b["state"] == VOTA and b["initial_weight"] == 0.25
    assert b["publicable"] is True
    assert b["dimensions"]["rendimiento"]["estado"] == "cumple"
    assert b["dimensions"]["evidencia"]["estado"] == "cumple"


def test_random_control_never_votes_or_validates(oracle):
    out = oracle[1]
    ctl = [a for a in out["attempts"] if a["control"]]
    assert ctl and all(a["verdict"] != "VALIDADA" for a in ctl)
    assert all(not c["id"].endswith("#control@v1") for c in out["bots"])   # el control no se puntúa
    assert only(out)["control"]["verdict"] != "VALIDADA"


def test_noise_bot_is_not_validated_and_is_rejected(mkt):
    out = run(mkt, noise_rows(mkt))
    b = only(out)
    assert b["verdict"]["verdict"] != "VALIDADA" and not b["publicable"]
    assert b["state"] in (RECHAZADO, INFORMA) and b["initial_weight"] == 0.0


def test_inverted_bot_is_rejected(mkt):
    b = only(run(mkt, oracle_rows(mkt, flip=True)))
    assert b["verdict"]["verdict"] == "RECHAZADA" and b["state"] == RECHAZADO


def test_no_security_never_votes_even_if_it_performs(mkt):
    rows = oracle_rows(mkt)
    out = run(mkt, rows, {BOT: card(enabled=False)},
              {"hummingbot-directional:s1@1h@v1": GOOD})
    b = only(out)
    assert b["verdict"]["verdict"] == "VALIDADA"      # rinde…
    assert b["state"] == DESHABILITADO and b["initial_weight"] == 0.0 and not b["publicable"]


def test_informs_when_safe_but_no_marginal_measured(oracle, mkt):
    out = run(mkt, oracle[0])                           # sin aporte medido
    b = only(out)
    assert b["verdict"]["verdict"] == "VALIDADA"
    assert b["state"] == INFORMA and b["initial_weight"] == 0.0 and b["publicable"] is True


def test_holm_counts_retired_versions(mkt):
    v1, v2 = version("1"), version("2")
    rows = [(s, c) for s, c in oracle_rows(mkt, ver=v1)]
    old = [(s, c) for s, c in noise_rows(mkt, ver=v2)]
    # v1 aparece primero (todas sus posturas empiezan antes); v2 = la versión vigente
    rows_two = [(s, c) for s, c in rows if s.asof < mkt.end - 60 * 24 * 3_600_000] + old
    out_two = run(mkt, rows_two)
    out_one = run(mkt, old)
    assert out_two["attempts_total"] == 4 and out_one["attempts_total"] == 2
    assert any(a["retired"] for a in out_two["attempts"])
    p2 = only(out_two)["verdict"]["p_holm"]
    p1 = only(out_one)["verdict"]["p_holm"]
    assert p2 >= p1                                     # más intentos nunca bajan el p ajustado


def test_no_future_in_the_gate(mkt, oracle):
    asof = mkt.end - 50 * 24 * 3_600_000
    out = run(mkt, oracle[0], asof=asof)
    v = only(out)["verdict"]
    assert v["n_oos"] < only(oracle[1])["verdict"]["n_oos"]
    att = next(a for a in out["attempts"] if not a["control"])
    assert att["oos"]["to"] <= asof and att["oos"]["after_asof"] > 0


def test_bot_costs_are_ignored_in_favor_of_t25(mkt):
    cheap = oracle_rows(mkt, costs={"taker_fee": 0.0, "maker_fee": 0.0})
    dear = oracle_rows(mkt, costs={"taker_fee": 0.05, "maker_fee": 0.05})
    i = identities(cheap)[0]
    a = shadow_trades(i, cheap, mkt.c1h, mkt.path, SYMBOL, mkt.regime_at)
    b = shadow_trades(i, dear, mkt.c1h, mkt.path, SYMBOL, mkt.regime_at)
    assert a and [t.r for t in a] == [t.r for t in b]
    assert all(t.cost_r > 0 for t in a)                  # costos de T25 presentes


def test_ideas_open_only_on_side_change_and_are_point_in_time(mkt):
    rows = oracle_rows(mkt)
    ideas = ideas_of(identities(rows)[0], rows, mkt.c1h, SYMBOL)
    assert 0 < len(ideas) < len(rows) / 3
    assert all(i.kind == "market" and i.t % 3_600_000 == 0 for i in ideas)
    c = {c.t: c.c for c in mkt.c1h}
    assert all(i.entry == c[i.t - 3_600_000] for i in ideas)    # cierre de la vela previa


def test_control_has_same_instants_and_geometry(mkt):
    rows = oracle_rows(mkt)
    i = identities(rows)[0]
    real, ctl = ideas_of(i, rows, mkt.c1h, SYMBOL), ideas_of(i, rows, mkt.c1h, SYMBOL,
                                                             control=True)
    assert [x.t for x in real] == [x.t for x in ctl]
    assert {x.side for x in ctl} == {-1, 1}
    assert all(abs(x.entry - x.sl) == pytest.approx(abs(y.entry - y.sl))
               for x, y in zip(real, ctl, strict=True))


def test_regime_report_is_info_only(oracle):
    r = oracle[1]["regimes"]
    assert set(r) >= {"rows", "passing", "selection_by_regime", "note"}
    assert r["selection_by_regime"] == bool(r["passing"])
