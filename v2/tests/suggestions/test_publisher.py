"""Publicador de sugerencias validadas (T50): solo VALIDADAS, con evidencia y motivo si no hay."""

from __future__ import annotations

from eim.suggestions.publisher import DATOS_VIEJOS, OK, SIN_SENAL, SIN_VALIDADAS, STATE
from tests.suggestions.helpers import ATR, NOW, PRICE, T1H, H, idea, run, verdict


def test_validated_with_live_idea_appears_with_evidence():
    pub = run([idea()], [verdict()])
    assert pub.status == OK and len(pub.setups) == 1
    s = pub.setups[0]
    assert (s["strategy"], s["timeframe"], s["version"], s["side"]) == ("ema", "1h", "v1", "long")
    assert s["state"] == STATE and s["created_at"] == T1H and s["rr"] == 2.0
    assert s["reason"] == "regla A; regla B"
    ev = s["evidence"]
    assert ev["n_oos"] == 240 and ev["ci95"] == [0.05, 0.25] and ev["p_holm"] == 0.03
    assert ev["max_dd"] == 0.18 and ev["win_rate"] == 0.47 and ev["cost_r"] == 0.12
    assert ev["n_live"] == 31 and ev["mean_live"] == 0.08


def test_observation_and_rejected_never_appear():
    for v in ("EN OBSERVACIÓN", "RECHAZADA"):
        pub = run([idea()], [verdict(verdict=v)])
        assert pub.setups == [] and pub.status == SIN_VALIDADAS
        assert "Ninguna estrategia pasa" in pub.message


def test_other_version_does_not_inherit_validation():
    pub = run([idea(version="fpB")], [verdict(fp="fpA")])
    assert pub.status == SIN_SENAL and pub.setups == []


def test_retired_validated_version_is_ignored():
    pub = run([idea()], [verdict(retired=NOW - H)])
    assert pub.status == SIN_VALIDADAS


def test_no_validated_means_empty_with_reason_and_counts():
    pub = run([idea()], [verdict(verdict="RECHAZADA"), verdict("rsi", verdict="EN OBSERVACIÓN")])
    assert pub.status == SIN_VALIDADAS and pub.setups == []
    assert pub.validation["counts"] == {"RECHAZADA": 1, "EN OBSERVACIÓN": 1}
    assert "1 en observación, 1 rechazadas" in pub.message


def test_validated_without_signal():
    pub = run([], [verdict()])
    assert pub.status == SIN_SENAL and "1 versión(es) validada(s)" in pub.message


def test_old_verdicts_or_heartbeat_mean_stale_data():
    assert run([idea()], [verdict()], verdicts_asof=NOW - 9 * H).status == DATOS_VIEJOS
    assert run([idea()], [verdict()], verdicts_asof=None).status == DATOS_VIEJOS
    assert run([idea()], [verdict()], heartbeat=NOW - 2 * H).status == DATOS_VIEJOS
    assert run([idea()], [verdict()], heartbeat=None).status == DATOS_VIEJOS
    assert run([idea()], [verdict()], view_stale=True).status == DATOS_VIEJOS
    assert run([idea()], [verdict()], price=None).status == DATOS_VIEJOS


def test_only_last_closed_candle_of_each_intraday_timeframe():
    older = idea(t=T1H - H)
    four_h = idea(tf="4h")
    pub = run([older, four_h], [verdict(), verdict(tf="4h")])
    assert pub.status == SIN_SENAL
    long_hold = idea(hold_h=48)
    assert run([long_hold], [verdict()]).status == SIN_SENAL


def test_expired_ideas_are_discarded():
    cases = {
        "sl": idea(entry=PRICE + 3, sl_d=1.0),                     # precio ya bajo el SL (largo)
        "tp": idea(entry=PRICE - 3, sl_d=1.0, rr=1.0),             # precio ya pasó el TP
        "drift": idea(entry=PRICE - 0.6 * ATR, sl_d=3.0),          # mercado: se alejó > 0,5 ATR
        "filled": idea(kind="limit", entry=PRICE + 0.5),           # límite ya tocada
        "window": idea(kind="limit", entry=PRICE - 1.0, t=NOW - 7 * H, fill_h=6.0),
    }
    for name, i in cases.items():
        pub = run([i], [verdict()], last_t={"1h": i.t})
        assert pub.setups == [] and pub.status == SIN_SENAL, name
        assert len(pub.discarded) == 1, name


def test_live_limit_inside_window_survives():
    pub = run([idea(kind="limit", entry=PRICE - 1.0)], [verdict()])
    assert pub.status == OK and pub.setups[0]["valid_until"] == T1H + 6 * H


def test_rank_by_ci_lower_bound_not_by_conf_and_dedup_by_side_and_entry():
    a = idea("a", conf=0.9, entry=PRICE)
    b = idea("b", conf=0.2, entry=PRICE + 0.2 * ATR)              # mismo lado, a < 0,5 ATR de b
    c = idea("c", conf=0.5, side=-1, entry=PRICE)                 # otro lado: no se deduplica
    d = idea("d", conf=0.5, entry=PRICE + 0.4 * ATR)
    vs = [verdict("a", ci_lo=0.01), verdict("b", ci_lo=0.30), verdict("c", ci_lo=0.10),
          verdict("d", ci_lo=0.20)]
    pub = run([a, b, c, d], vs)
    assert [s["strategy"] for s in pub.setups] == ["b", "c"]      # a y d caen contra b
    assert [s["strategy"] for s in run([a, c], vs).setups] == ["c", "a"]


def test_at_most_three():
    ideas = [idea(f"s{k}", kind="limit", entry=PRICE - 1.0 - 1.5 * k, sl_d=1.0, rr=12)
             for k in range(6)]
    vs = [verdict(f"s{k}", ci_lo=0.01 * k) for k in range(6)]
    pub = run(ideas, vs)
    assert [s["strategy"] for s in pub.setups] == ["s5", "s4", "s3"]


def test_observation_idea_goes_to_watch_never_to_setups():
    pub = run([idea()], [verdict(verdict="EN OBSERVACIÓN")])
    assert pub.status == SIN_VALIDADAS and pub.setups == []
    (w,) = pub.watch
    assert w["state"] == "observacion_no_validada" and w["verdict"] == "EN OBSERVACIÓN"
    assert w["strategy"] == "ema"


def test_rejected_never_in_watch():
    assert run([idea()], [verdict(verdict="RECHAZADA")]).watch == []


def test_watch_excludes_validated_and_expired_ideas():
    pub = run([idea("ema"), idea("rsi", entry=150.0)],
              [verdict("ema"), verdict("rsi", verdict="EN OBSERVACIÓN")])
    assert [s["strategy"] for s in pub.setups] == ["ema"] and pub.watch == []


def test_watch_ordered_by_sample_and_deduplicated():
    vs = [verdict(f"s{k}", verdict="EN OBSERVACIÓN") | {"n_oos": k} for k in range(3)]
    ideas = [idea("s0", side=1), idea("s1", side=-1), idea("s2", side=1)]
    pub = run(ideas, vs)
    assert [w["strategy"] for w in pub.watch] == ["s2", "s1"]   # s0: mismo lado y entrada que s2
