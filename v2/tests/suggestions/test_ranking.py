"""Ranking de las tres posiciones y embudo de estados (T122): solo validadas, sin rellenos."""

from __future__ import annotations

import pytest

from eim.suggestions.ranking import ORDER_RULE, SLOTS, funnel, ranking, success_of, wilson
from tests.suggestions.helpers import ATR, NOW, PRICE, T1H, H, idea, run, verdict

LAST = {"15m": T1H, "1h": T1H}


def board(cands, vs, **kw):
    """Publica como la ruta (sin las ideas ya descartadas por la sombra) y arma el tablero."""
    pub = run([i for i, st in cands if st not in ("CANCELADA", "RECHAZADA", "CERRADA")], vs, **kw)
    statuses = {i.id: st for i, st in cands}
    fun = funnel(cands, vs, pub, last_t=kw.get("last_t", LAST), now=NOW,
                 price=kw.get("price", PRICE), atr=ATR, review=kw.get("review", ()))
    return pub, ranking(pub, atr=ATR, statuses=statuses), fun


def test_always_three_slots_and_only_validated_fill_them():
    a, b = idea("a"), idea("b", side=-1)
    pub, slots, _ = board([(a, "PENDIENTE"), (b, "ABIERTA")],
                          [verdict("a", ci_lo=0.05), verdict("b", ci_lo=0.20)])
    assert len(slots) == SLOTS == 3
    assert [s["state"] for s in slots] == ["validada", "validada", "vacia"]
    assert [pub.setups[s["index"]]["strategy"] for s in slots[:2]] == ["b", "a"]   # IC95 inferior
    assert [s["rank"] for s in slots] == [1, 2, 3]
    assert slots[0]["sim_status"] == "ABIERTA" and slots[1]["sim_status"] == "PENDIENTE"
    assert slots[0]["order"] == {"rule": ORDER_RULE, "ci_low": 0.20}
    assert "no se rellena" in slots[2]["message"] and slots[2]["index"] is None


@pytest.mark.parametrize("v", ["EN OBSERVACIÓN", "RECHAZADA"])
def test_unvalidated_ideas_never_take_a_slot(v):
    pub, slots, _ = board([(idea(), "PENDIENTE")], [verdict(verdict=v)])
    assert pub.setups == [] and all(s["state"] == "vacia" for s in slots)
    assert all("puerta de validación" in s["message"] for s in slots)


def test_empty_slots_explain_stale_data_and_missing_signal():
    _, slots, _ = board([(idea(), "PENDIENTE")], [verdict()], verdicts_asof=NOW - 9 * H)
    assert all(s["state"] == "vacia" and "Datos desactualizados" in s["message"] for s in slots)
    _, slots, _ = board([], [verdict()])
    assert all("no proponen una operación" in s["message"] for s in slots)


def test_success_is_observed_frequency_with_wilson_interval_never_calibrated():
    s = success_of({"n_oos": 240, "win_rate": 0.47})
    assert s["wins"] == 113 and s["n"] == 240 and s["calibrated"] is False
    lo, hi = s["ci95"]
    assert lo < 0.47 < hi and hi - lo < 0.15 and "no es una probabilidad calibrada" in s["note"]
    assert success_of({"n_oos": 0, "win_rate": None})["win_rate"] is None
    assert wilson(0, 0) is None and wilson(10, 10)[1] == 1.0


def test_slot_lists_invalidation_and_context_risks():
    i = idea(kind="limit", entry=PRICE - 1.0)
    i = i.__class__(**{**i.__dict__, "htf": -1, "syn_bias": 0.4})      # largo contra la síntesis
    pub, slots, _ = board([(i, "PENDIENTE")], [verdict()])
    kinds = [x["kind"] for x in slots[0]["invalidation"]]
    assert kinds == ["sl", "tp", "window", "filled"]
    assert slots[0]["invalidation"][2]["until"] == T1H + 6 * H
    risks = {x["kind"] for x in slots[0]["risks"]}
    assert "htf_against" in risks and "max_dd" in risks and "synthesis_against" not in risks
    short = idea(side=-1)
    short = short.__class__(**{**short.__dict__, "syn_bias": 0.4})
    _, slots, _ = board([(short, "PENDIENTE")], [verdict()])
    assert {x["kind"] for x in slots[0]["risks"]} >= {"synthesis_against"}
    drift = next(x for x in slots[0]["invalidation"] if x["kind"] == "drift")
    assert drift["lo"] == pytest.approx(PRICE - 0.5 * ATR)
    assert drift["hi"] == pytest.approx(PRICE + 0.5 * ATR)


def test_funnel_classifies_every_idea_of_the_last_candle():
    ok, dup = idea("ok"), idea("dup", entry=PRICE + 0.1)              # dup: mismo lado y entrada
    obs, rej, new = idea("obs", side=-1), idea("rej"), idea("new")
    dead = idea("dead")
    gone = idea("gone", entry=PRICE + 3, sl_d=1.0)                    # precio ya bajo su SL
    old = idea("old", t=T1H - H)                                      # otra vela: fuera del embudo
    vs = [verdict("ok", ci_lo=0.3), verdict("dup", ci_lo=0.1),
          verdict("obs", verdict="EN OBSERVACIÓN"), verdict("rej", verdict="RECHAZADA"),
          verdict("dead"), verdict("gone"), verdict("old")]
    cands = [(ok, "PENDIENTE"), (dup, "PENDIENTE"), (obs, "PENDIENTE"), (rej, "PENDIENTE"),
             (new, "PENDIENTE"), (dead, "CANCELADA"), (gone, "PENDIENTE"), (old, "PENDIENTE")]
    pub, slots, f = board(cands, vs)
    assert [s["strategy"] for s in pub.setups] == ["ok"]
    assert (f["identified"], f["analyzed"], f["unanalyzed"]) == (7, 6, 1)
    assert (f["validated"], f["ranked"], f["pending"], f["discarded"]) == (4, 1, 1, 4)
    reasons = {r["reason"]: r["n"] for r in f["reasons"]}
    assert reasons == {"duplicada o fuera de las tres primeras": 1,
                       "rechazada por la puerta de validación (T49)": 1,
                       "el bróker simulado la dio por cancelada": 1,
                       "el precio ya está más allá del SL": 1}
    assert f["candles"] == LAST and f["timeframes"] == ["15m", "1h"]


def test_funnel_marks_versions_in_review_as_discarded():
    _, slots, f = board([(idea(), "PENDIENTE")], [verdict()], review=("ema@1h@v1",))
    assert slots[0]["state"] == "vacia" and f["validated"] == 0 and f["discarded"] == 1
    assert f["reasons"][0]["reason"].startswith("validada, en revisión")
