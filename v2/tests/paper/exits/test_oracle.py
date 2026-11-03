"""T133 — la cota del oráculo de M4 (E6): que mida el techo correcto y que no se autoengañe.

Lo que hay que demostrar es que el veredicto se juzga con el **oráculo por día** (la cota que
pre-registra E6) y no con la envolvente por operación, que elige sabiendo ya cómo acabó cada
operación y por eso cumpliría casi cualquier criterio sin significar nada.
"""

from __future__ import annotations

import pytest

from eim.paper.exits import bench, metrics, oracle
from eim.paper.exits.bench import Row
from tests.paper.exits.helpers import trade

M0, M1 = "M0 first_r=0.1", "M1 be=1/0.1"
DAY_MS = 86_400_000


def row(iid: str, day: int, r0: float, r1: float) -> Row:
    a = trade(r0, day=day, tid=iid, policy=M0)
    b = trade(r1, day=day, tid=iid, policy=M1)
    return Row(iid, a.t, 1.0, {M0: a, M1: b}, {M0: "CERRADA", M1: "CERRADA"})


def make(rows: list[Row]) -> bench.Bench:
    return bench.Bench(tuple(rows), (M0, M1), 0, {M0: {}, M1: {}})


def labeler_of(by_day: dict[int, str]):
    """Etiquetador de prueba: día UTC → etiqueta de tendencia."""
    return lambda t: (by_day.get(t // DAY_MS - trade(0.0).t // DAY_MS, oracle.NO_DATA),)


def test_the_day_oracle_takes_the_policy_the_map_declares():
    rows = [row("a", 0, -1.0, +2.0), row("b", 1, +0.5, -1.0), row("c", 2, 0.0, 0.0)]
    lab = labeler_of({0: oracle.TREND, 1: oracle.RANGE, 2: oracle.MIDDLE})
    got, counts = oracle.pick_by_day(make(rows), lab,
                                     {oracle.TREND: M1, oracle.RANGE: M0, oracle.MIDDLE: M0})
    assert [t.r for t in got] == [2.0, 0.5, 0.0]       # tendencia→M1, lateral→M0, intermedio→M0
    assert counts == {oracle.TREND: 1, oracle.RANGE: 1, oracle.MIDDLE: 1}
    assert {t.policy for t in got} == {"M4_oraculo"}   # se reetiqueta, no se mezcla con las bases


def test_a_day_without_a_declared_policy_is_counted_and_left_out():
    rows = [row("a", 0, -1.0, +2.0), row("b", 1, +0.5, -1.0)]
    lab = labeler_of({0: oracle.TREND, 1: "brusco"})
    got, counts = oracle.pick_by_day(make(rows), lab, {oracle.TREND: M1})
    assert [t.id for t in got] == ["a"]
    assert counts[oracle.NO_DATA] == 1                 # la etiqueta sin política se informa


def test_the_envelope_takes_the_best_of_each_trade_and_counts_who_won():
    rows = [row("a", 0, -1.0, +2.0), row("b", 1, +0.5, -1.0), row("c", 2, 0.3, 0.3)]
    got, wins = oracle.pick_best(make(rows), [M0, M1])
    assert [t.r for t in got] == [2.0, 0.5, 0.3]
    assert wins[M0] == 2 and wins[M1] == 1             # el empate se queda con el primero
    assert {t.policy for t in got} == {"M4_envolvente"}


def test_the_envelope_is_never_worse_than_either_base():
    rows = [row(f"i{k}", k, (-1) ** k * 0.5, (-1) ** (k + 1) * 0.4) for k in range(20)]
    b = make(rows)
    env, _ = oracle.pick_best(b, [M0, M1])
    e = metrics.summary(env)["expectancy_r"]
    for base in (M0, M1):
        assert e >= metrics.summary(b.trades(base))["expectancy_r"]


def test_the_paired_differences_only_use_the_shared_entries():
    rows = [row("a", 0, -1.0, +2.0), row("b", 1, +0.5, -1.0)]
    b = make(rows)
    env, _ = oracle.pick_best(b, [M0, M1])
    d = oracle.diffs_vs(env, b.trades(M0))
    assert [x[1] for x in d] == [3.0, 0.0]
    assert oracle.diffs_vs(env, []) == []              # sin base común no hay diferencias


BASE = {"expectancy_r": -0.15, "pf": 0.39, "max_dd_r": 4591.0, "cvar95_r": -1.35,
        "win_loss_ratio": 0.12}


def cand(exp=-0.09, pf=0.74, dd=2812.0, cvar=-1.37, ratio=0.35) -> dict:
    return {"expectancy_r": exp, "pf": pf, "max_dd_r": dd, "cvar95_r": cvar,
            "win_loss_ratio": ratio}


def test_the_real_case_of_t133_fails_criteria_2_and_3():
    """Las cifras medidas: el oráculo mejora la esperanza y sigue sin cumplir."""
    got = oracle.criteria_1_to_3(cand(), BASE, (0.0453, 0.0758), 1.15, 1.1)
    assert got["c1_delta_positivo"] is True            # Δ +0,060 con IC sobre 0
    assert got["c2_cociente_y_pf"] is False            # cociente 0,35 < 0,50
    assert got["c3_dd_y_cvar"] is False                # CVaR −1,37 peor que −1,35
    assert got["cumple_1_a_3"] is False


def test_a_candidate_that_meets_everything_is_recognised():
    got = oracle.criteria_1_to_3(cand(exp=0.21, pf=1.85, dd=45.0, cvar=-1.349, ratio=0.52),
                                 BASE, (0.3494, 0.3786), 1.15, 1.1)
    assert (got["c1_delta_positivo"], got["c2_cociente_y_pf"], got["c3_dd_y_cvar"]) == (
        True, True, True)
    assert got["cumple_1_a_3"] is True


def test_an_interval_that_touches_zero_fails_the_first_criterion():
    got = oracle.criteria_1_to_3(cand(), BASE, (-0.001, 0.12), 1.15, 1.1)
    assert got["c1_delta_positivo"] is False


def test_a_missing_interval_leaves_the_criterion_pending_not_passed():
    got = oracle.criteria_1_to_3(cand(), BASE, (float("nan"), float("nan")), 1.15, 1.1)
    assert got["c1_delta_positivo"] is None and got["cumple_1_a_3"] is False


def test_the_verdict_judges_the_day_oracle_and_not_the_envelope():
    """Si la envolvente cumple y el oráculo no, M4 se descarta: es el caso real de T133."""
    checks = {
        "M4_oraculo": {M0: oracle.criteria_1_to_3(cand(), BASE, (0.045, 0.076), 1.15, 1.1),
                       M1: oracle.criteria_1_to_3(cand(), BASE, (0.046, 0.073), 1.15, 1.1)},
        "M4_envolvente": {M0: oracle.criteria_1_to_3(
            cand(exp=0.21, pf=1.85, dd=45.0, cvar=-1.349, ratio=0.52), BASE,
            (0.349, 0.379), 1.15, 1.1)},
    }
    out = oracle.verdict(checks)
    assert out.startswith("M4 SE DESCARTA")
    assert "criterio 2" in out and "criterio 2 (cociente y PF) y el 3" in out
    assert "envolvente" not in out                     # la envolvente no decide


def test_the_verdict_says_there_is_headroom_when_the_day_oracle_meets_everything():
    good = oracle.criteria_1_to_3(cand(exp=0.21, pf=1.85, dd=45.0, cvar=-1.349, ratio=0.52),
                                  BASE, (0.349, 0.379), 1.15, 1.1)
    out = oracle.verdict({"M4_oraculo": {M0: good, M1: good}})
    assert "CUMPLE" in out and "merece la pena buscar rasgos" in out


def test_without_data_the_verdict_does_not_invent_one():
    assert oracle.verdict({}) == "sin datos para concluir"
    assert oracle.verdict({"M4_envolvente": {}}) == "sin datos para concluir"


def test_the_report_renders_the_verdict_and_both_bounds():
    from eim.paper.exits.oracle_report import render

    res = {
        "meta": {"symbol": "BTCUSDT", "prereg": "prereg_t131_v2", "prereg_sha256": "0" * 64,
                 "built": "2026-11-03T19:00+00:00", "data": "copia", "commit": "abc1234",
                 "fine_bars": 2_019_972},
        "window": {"from": "2023-01-11T10:00+00:00", "to": "2026-08-16T00:00+00:00",
                   "folds": 10, "embargo_hours": 200.0},
        "bench": {"ideas": 60720, "paired": 45822},
        "policy_by_day": {"Lateral": M0}, "day_counts": {"Lateral": 13474},
        "envelope_wins": {M0: 28794, M1: 17028},
        "metrics": {M0: metrics.summary([trade(-0.2)]),
                    "M4_oraculo": metrics.summary([trade(-0.1)])},
        "checks": {"M4_oraculo": {M0: oracle.criteria_1_to_3(cand(), BASE, (0.045, 0.076),
                                                             1.15, 1.1)}},
        "verdict": "M4 SE DESCARTA (E6): prueba",
    }
    md = render(res)
    for piece in ("# T133", "M4 SE DESCARTA", "M4_oraculo", "M4_envolvente",
                  "Lo que esto NO dice", "no prueba nada"):
        assert piece in md, piece


def test_an_empty_bench_gives_empty_bounds():
    b = make([])
    assert oracle.pick_by_day(b, labeler_of({}), {oracle.TREND: M1}) == ([], {})
    env, wins = oracle.pick_best(b, [M0, M1])
    assert env == [] and wins == {M0: 0, M1: 0}


@pytest.mark.parametrize("missing", [M0, M1])
def test_a_row_the_other_policy_could_not_close_is_not_paired(missing: str):
    r = row("a", 0, -1.0, 2.0)
    broken = Row(r.id, r.t, r.qty, {**r.by_policy, missing: None}, r.status)
    b = bench.Bench((broken,), (M0, M1), 0, {M0: {}, M1: {}})
    assert b.paired() == []
    assert oracle.pick_best(b, [M0, M1])[0] == []
