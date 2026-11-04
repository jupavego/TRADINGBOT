"""T132 — el MAE de las ganadoras sin fuga ni circularidad (E5), para M8 y la fase de M5.

La prueba que exige la aceptación de T132 es
`test_the_quantile_of_a_fold_ignores_everything_in_its_test_span`: el cuantil de un pliegue no
puede cambiar si se alteran las operaciones de su tramo de prueba. Si cambiara, el stop inicial
sabría cómo acabaron las operaciones que va a medir.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.paper.exits import winners_mae as wm
from eim.paper.exits.walkforward import Fold
from tests.paper.exits.helpers import trade
from tests.paper.exits.test_walkforward import at, fold, ms

DAY = 86_400_000
REF = "M1 be=1/0.1 (referencia fija pre-registrada)"


def win(tid: str, when: int, mae: float, r: float = 0.5, sid: str = "s@1h"):
    """Operación cerrada con su MAE en R; `r > 0` la hace ganadora para la referencia."""
    t = trade(r, tid=tid, mae=mae, hours=1)
    return type(t)(**{**at(t, when).__dict__, "sid": sid})


def ratio_one(_t) -> float:
    """σ = riesgo: el MAE en R y en σ coinciden, así los números del test se leen solos."""
    return 1.0


def test_the_quantile_comes_from_the_winners_of_the_fit_span():
    f = fold()
    rows = [win(f"w{k}", f.fit_from + (k + 1) * DAY, mae=0.1 + 0.01 * k) for k in range(40)]
    rows += [win(f"l{k}", f.fit_from + (k + 1) * DAY, mae=0.9, r=-1.0) for k in range(40)]
    got = wm.fit_fold(rows, f, ratio_one, reference=REF, quantile=0.9, min_trades=30)
    assert got.n_winners == 40 and got.of("s@1h") is not None
    # las perdedoras (MAE 0,9) no entran: el cuantil 0,9 de 0,10…0,49 queda muy por debajo
    assert got.of("s@1h") == pytest.approx(np.quantile([0.1 + 0.01 * k for k in range(40)], 0.9))
    assert got.reference == REF


def test_the_quantile_of_a_fold_ignores_everything_in_its_test_span():
    """Aceptación de T132: alterar el tramo de prueba no cambia el cuantil del ajuste."""
    f = fold()
    fit = [win(f"w{k}", f.fit_from + (k + 1) * DAY, mae=0.2 + 0.005 * k) for k in range(40)]
    test = [win(f"t{k}", f.test_from + (k + 1) * DAY, mae=0.2 + 0.005 * k) for k in range(20)]
    base = wm.fit_fold(fit + test, f, ratio_one, reference=REF, min_trades=30)
    # se reescriben POR COMPLETO las operaciones del tramo de prueba
    other = [win(f"t{k}", f.test_from + (k + 1) * DAY, mae=50.0, r=9.0) for k in range(20)]
    again = wm.fit_fold(fit + other, f, ratio_one, reference=REF, min_trades=30)
    assert again.by_sid == base.by_sid
    assert again.n_by_sid == base.n_by_sid and again.n_winners == base.n_winners
    # y además ninguna operación del ajuste viene de la prueba
    assert wm.leak_check(fit + test, f) == []


def test_a_trade_that_closes_inside_the_test_span_is_purged_from_the_quantile():
    f = fold()
    fit = [win(f"w{k}", f.fit_from + (k + 1) * DAY, mae=0.2) for k in range(35)]
    crossing = at(trade(0.5, tid="cruza", mae=99.0, hours=1), f.fit_to - DAY,
                  f.test_from + DAY)
    with_cross = wm.fit_fold([*fit, crossing], f, ratio_one, reference=REF, min_trades=30)
    assert with_cross.n_by_sid["s@1h"] == 35          # la que cruza no cuenta
    assert with_cross.of("s@1h") == pytest.approx(0.2)


def test_without_the_minimum_sample_there_is_no_quantile_and_nothing_tightens():
    f = fold()
    rows = [win(f"w{k}", f.fit_from + (k + 1) * DAY, mae=0.2) for k in range(5)]
    got = wm.fit_fold(rows, f, ratio_one, reference=REF, min_trades=30)
    assert got.of("s@1h") is None and got.n_by_sid["s@1h"] == 5
    assert got.to_json()["sids"] == {}


def test_each_strategy_timeframe_gets_its_own_quantile():
    f = fold()
    rows = [win(f"a{k}", f.fit_from + (k + 1) * DAY, mae=0.2, sid="a@1h") for k in range(40)]
    rows += [win(f"b{k}", f.fit_from + (k + 1) * DAY, mae=2.0, sid="b@4h") for k in range(40)]
    got = wm.fit_fold(rows, f, ratio_one, reference=REF, min_trades=30)
    assert got.of("a@1h") == pytest.approx(0.2)
    assert got.of("b@4h") == pytest.approx(2.0)
    assert got.of("c@1h") is None                     # una estrategia sin muestra no hereda


def test_a_trade_without_sigma_does_not_count():
    f = fold()
    rows = [win(f"w{k}", f.fit_from + (k + 1) * DAY, mae=0.2) for k in range(40)]
    got = wm.fit_fold(rows, f, lambda _t: None, reference=REF, min_trades=1)
    assert got.n_winners == 40 and got.by_sid == {}    # se cuentan, pero no se usan


def test_each_decision_takes_the_quantile_of_its_own_fold():
    f0 = fold()
    f1 = Fold(1, ms("2023-04-01T00:00:00"), ms("2024-04-01T00:00:00"),
              ms("2024-04-01T00:00:00"), ms("2024-07-01T00:00:00"), 2 * DAY)
    # `a` cae solo en el ajuste de f0; `b`, en el ajuste de f1 y en la PRUEBA de f0 (los
    # pliegues se solapan por diseño, y cada cuantil usa su propio tramo de ajuste).
    a = [win(f"a{k}", f0.fit_from + (k + 1) * DAY, mae=0.2) for k in range(40)]
    b = [win(f"b{k}", f0.test_from + (k + 1) * DAY, mae=0.8) for k in range(40)]
    by = wm.build(a + b, [f0, f1], ratio_one, reference=REF, min_trades=30)
    q = by.quantile_of()
    assert q("s@1h", f0.test_from + DAY) == pytest.approx(0.2)
    assert q("s@1h", f1.test_from + DAY) == pytest.approx(0.8)
    assert q("s@1h", f0.fit_from) is None             # fuera de todo tramo de prueba
    assert by.at(f0.fit_from) is None
    assert len(by.to_json()["folds"]) == 2


def test_the_survival_threshold_falls_back_to_the_base_without_data():
    f = fold()
    rows = [win(f"w{k}", f.fit_from + (k + 1) * DAY, mae=0.4) for k in range(40)]
    got = wm.fit_fold(rows, f, ratio_one, reference=REF, min_trades=30)
    assert wm.survival_r_of(got, "s@1h", 1.0, base=0.1) == pytest.approx(0.4)
    assert wm.survival_r_of(got, "otra@1h", 1.0, base=0.1) == pytest.approx(0.1)
    assert wm.survival_r_of(None, "s@1h", 1.0, base=0.1) == pytest.approx(0.1)
    assert wm.survival_r_of(got, "s@1h", None, base=0.1) == pytest.approx(0.1)


def test_the_leak_check_catches_a_trade_counted_on_both_sides():
    """La misma operación no puede alimentar el cuantil y estar en el tramo que se mide."""
    f = fold()
    only_fit = at(trade(0.5, tid="x", hours=1), f.fit_from + DAY)
    assert wm.leak_check([only_fit], f) == []
    same_id_in_test = type(only_fit)(**{**only_fit.__dict__, "t": f.test_from + DAY})
    found = wm.leak_check([only_fit, same_id_in_test], f)
    assert found and "x" in found[0] and "pliegue 0" in found[0]
