"""T139: la regla de lectura y la recomendación hacen lo que fijó el pre-registro."""

from __future__ import annotations

from eim.validation.gate import OBSERVACION, Check, Measure, Verdict
from eim.validation.hypotheses import decision as dc
from eim.validation.hypotheses import pipeline as pp
from eim.validation.lineage import Version


def _verdict(oks: dict[str, bool | None], n: int = 300, verdict: str = OBSERVACION,
             strategy: str = "x") -> Verdict:
    v = Version(f"{strategy}@1h", 1, "f", strategy, "1h", 0, None, "T139")
    m = Measure("x", 0, n, 0, 0, 0.1, 0.05, {}, (0.0, 0.2), 0.001, 10, 0.1, 0.1, [], 0, None, 0.1,
                (None, None))
    checks = tuple(Check(k, k, None, "", oks.get(k, True), "") for k in
                   ("V1", "V2", "V3", "V4", "V5", "V6"))
    return Verdict(v, m, verdict, "", checks, 0.01, "validation_v1", ())


def _sides(**kw) -> pp.SideStats:
    base = dict(n=300, gross=0.3, cost=0.1, n_long=150, n_short=150, gross_long=0.3,
                gross_short=0.3, balanced=0.3, stressed=0.1)
    return pp.SideStats(**{**base, **kw})


def _key(oks=None, null=0.1, bank=0.1, control=True, strategy="x", **sides) -> dc.KeyReading:
    return dc.KeyReading(_verdict(oks or {}, strategy=strategy), _sides(**sides), null, bank,
                         control)


def test_a_key_follows_only_with_all_five_conditions():
    assert dc.state_of(_key()) == dc.SIGUE
    assert dc.state_of(_key(oks={"V5": None})) == dc.SIGUE       # el tramo en vivo, pendiente
    for bad in (_key(oks={"V3": False}), _key(oks={"V5": False}), _key(balanced=0.05),
                _key(balanced=None), _key(stressed=-0.01), _key(null=0.5), _key(control=False),
                _key(control=None), _key(bank=-0.01)):
        assert dc.state_of(bad) == dc.FUERA


def test_the_bank_only_discards_and_no_trades_there_do_not_discard():
    assert dc.conditions(_key(bank=None))["5_banco"] is True
    assert dc.conditions(_key(bank=0.0))["5_banco"] is True
    assert dc.conditions(_key(bank=-0.001))["5_banco"] is False


def test_no_sample_with_balanced_gross_over_cost_stays_in_observation():
    assert dc.state_of(_key(oks={"V1": False})) == dc.OBSERVACION
    assert dc.state_of(_key(oks={"V1": False}, balanced=0.05)) == dc.FUERA


def test_recommendations():
    good = _key(strategy="a")
    bad = _key(balanced=0.0, strategy="b")
    watch = _key(oks={"V1": False}, strategy="c")
    assert dc.recommend([bad], [True])["code"] == "P1"
    assert dc.recommend([good, bad], [True])["follow"] == ["a@1h@v1"]
    assert dc.recommend([bad, watch], [True])["code"] == "OBSERVACION"
    assert dc.recommend([good, bad], [True])["code"] == "SIGUE"
    assert dc.recommend([good], [False])["code"] == "CONTROL"
    assert dc.recommend([bad], [None])["code"] == "P1"
