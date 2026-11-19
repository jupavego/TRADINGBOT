"""T190–T193: boleta de dirección, veredicto pre-registrado, sombras walk-forward y vigía."""

from __future__ import annotations

import numpy as np
import pytest

from eim.direction.board import Instant, build, outcomes_at, ref_index, regime_at
from eim.direction.params import SYNTH_ID, DirectionParams
from eim.direction.score import CONTRARY, EDGE, NO_VERDICT, judge, non_overlap, scoreboard
from eim.direction.shadow import ABSTAIN, WEIGHTED, compare, gate, walk
from eim.direction.stats import holm, wilson
from eim.direction.watch import ALERT, OK, SUSTAINED, WATCH, assess, compact, streak

STEP = 3_600_000
P = DirectionParams(regime_bars=8, regime_lookback=40)


def market(n: int = 6000, seed: int = 7):
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=np.int64) * STEP
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    return t, c


def history(t, c, start=100, stride=1, seed=3, oracle_acc=0.7, extra=()):
    """oracle acierta ~70 % de la dirección a 4 velas, noise es una moneda, anti se equivoca."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(start, len(t) - 1, stride):
        asof = int(t[i] + STEP)
        fut = np.sign(c[min(i + 4, len(c) - 1)] - c[i]) or 1.0
        good = fut if rng.random() < oracle_acc else -fut
        rows.append((asof, "oracle", 0.5 * good, 0.8, "ok"))
        rows.append((asof, "noise", float(rng.choice([-0.4, 0.4])), 0.8, "ok"))
        rows.append((asof, "anti", -0.5 * fut if rng.random() < 0.7 else 0.5 * fut, 0.8, "ok"))
        rows.append((asof, "regime", 0.9, 0.9, "ok"))           # excluido por su papel
        rows.append((asof, "weak", 0.01, 0.9, "ok"))            # bajo el umbral de voto
        rows.extend((asof, *e) for e in extra)
    return rows


def noise_synth(asof, rows):
    return next((b for a, b, *_ in rows if a == "noise"), None)


def test_ref_index_outcomes_and_regime():
    t, c = market(200)
    assert ref_index(t, int(t[10] + STEP), STEP) == 10
    assert ref_index(t, int(t[10] + STEP // 2), STEP) == 9      # vela en curso: la anterior
    assert ref_index(t, -5 * STEP, STEP) is None
    out = outcomes_at(t, c, 10, STEP, (1, 4, 500))
    assert out[4] == (1 if c[14] > c[10] else -1) and 500 not in out
    assert regime_at(c, 20, P) is None
    assert regime_at(c, 150, P) in ("baja", "media", "alta")


def test_build_filters_votes_and_scores_synthesis():
    t, c = market(800)
    votes, inst = build(history(t, c), t, c, STEP, P, noise_synth)
    agents = {v.agent for v in votes}
    assert agents == {"oracle", "noise", "anti", SYNTH_ID}
    assert all(i.synth in (-1, 1) for i in inst)
    assert inst[-1].outcome is None                              # el futuro aún no ocurrió


def test_non_overlap_spacing():
    t, c = market(800)
    votes, _ = build(history(t, c), t, c, STEP, P)
    kept = non_overlap([v for v in votes if v.agent == "oracle"], 4, STEP)
    gaps = np.diff([v.asof for v in kept])
    assert (gaps >= 4 * STEP).all()


def test_verdicts_follow_prereg():
    t, c = market()
    votes, _ = build(history(t, c), t, c, STEP, P, noise_synth)
    board = scoreboard(votes, STEP, P)
    judge({"BTC|1h": board}, P)
    prim = board[P.primary]
    assert prim["oracle"]["verdict"] == EDGE and prim["oracle"]["acc_eff"] > 0.62
    assert prim["noise"]["verdict"] not in (EDGE,)
    assert prim["anti"]["verdict"] == CONTRARY
    assert 0.4 < prim[SYNTH_ID]["acc_eff"] < 0.6


def test_small_sample_gives_no_verdict():
    t, c = market(400)
    votes, _ = build(history(t, c), t, c, STEP, P)
    board = scoreboard(votes, STEP, P)
    judge({"x": board}, P)
    assert board[P.primary]["oracle"]["verdict"] == NO_VERDICT


def test_holm_and_wilson():
    adj = holm({"a": 0.01, "b": 0.04, "c": None, "d": 0.03})
    assert adj["a"] == pytest.approx(0.03) and adj["c"] is None
    assert adj["b"] >= adj["d"] >= adj["a"]
    lo, hi = wilson(70, 100)
    assert lo > 0.5 and hi < 0.8 and wilson(0, 0) is None


def test_shadow_walk_has_no_lookahead():
    t, c = market(3000)
    p = P.model_copy(update={"qualify_min": 30})
    _, inst = build(history(t, c), t, c, STEP, p, noise_synth)
    k = 1500
    base = walk(inst, STEP, p)[k]
    tampered = [Instant(i.asof, i.regime, dict(i.votes), i.synth,
                        (-i.outcome if i.outcome else i.outcome) if j >= k - 3 else i.outcome)
                for j, i in enumerate(inst)]
    again = walk(tampered, STEP, p)[k]
    assert base[ABSTAIN] == again[ABSTAIN] and base["weights"] == again["weights"]


def test_shadows_beat_coin_synthesis_and_gate():
    t, c = market(6000)
    p = P.model_copy(update={"qualify_min": 30, "gate_min_pairs": 100})
    extra = []
    _, inst = build(history(t, c, extra=extra), t, c, STEP, p, noise_synth)
    dec = walk(inst, STEP, p)
    res = {n: compare(dec, n, STEP, p) for n in (ABSTAIN, WEIGHTED)}
    w = res[WEIGHTED]
    assert w["n_pairs"] > 100 and w["acc_shadow"] > w["acc_synth"] + 0.05
    assert 0 < w["coverage"] <= 1 and w["now"]["decision"] in (-1, 0, 1)
    gate({f"BTC|1h|{n}": r for n, r in res.items()}, p)
    assert w["passes"] is True


def test_abstain_needs_two_qualified():
    t, c = market(3000)
    p = P.model_copy(update={"qualify_min": 30})
    _, inst = build(history(t, c), t, c, STEP, p, noise_synth)
    dec = walk(inst, STEP, p)
    assert all(d[ABSTAIN] == 0 for d in dec)                    # solo oracle califica: no entra


def _board(syn_acc, syn_n, edge=()):
    prim = {SYNTH_ID: {"n_eff": syn_n, "acc_eff": syn_acc,
                       "ci95": wilson(int(syn_acc * syn_n), syn_n), "verdict": None},
            "noise": {"n_eff": 300, "acc_eff": 0.5, "ci95": [0.44, 0.56], "verdict": "sin_ventaja"}}
    for a in edge:
        prim[a] = {"n_eff": 300, "acc_eff": 0.6, "ci95": [0.55, 0.65], "verdict": EDGE}
    return {P.primary: prim}


def test_assess_states():
    assert assess(_board(0.5, 300, edge=("oracle",)), P, None)["state"] == OK
    assert assess(_board(0.5, 300), P, None)["state"] == WATCH
    assert assess(_board(0.40, 400), P, None)["state"] == ALERT
    assert assess(_board(0.40, 400), P, ALERT)["state"] == SUSTAINED


def test_streak_and_compact():
    hist = [{"symbol": "S", "timeframe": "1h", "shadows": {ABSTAIN: {"passes": True}}}]
    assert streak(hist, "S", "1h", ABSTAIN, True) == 2
    assert streak(hist, "S", "1h", ABSTAIN, False) == 0
    t, c = market(800)
    votes, _ = build(history(t, c), t, c, STEP, P)
    board = scoreboard(votes, STEP, P)
    judge({"x": board}, P)
    out = compact(board, P)
    assert set(out) == {"1", "4", "12"} and "by_regime" in out["4"]["oracle"]
