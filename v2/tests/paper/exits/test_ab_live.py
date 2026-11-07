"""T135 — A/B prospectivo de M8: congelado antes de empezar y sin veredicto antes de tiempo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import eim
from eim.paper.exits import ab_live, bench, features, grid, power
from eim.paper.exits.bench import BenchTrade
from eim.paper.exits.prereg import load_prereg
from eim.paper.exits.winners_mae import WinnersMae
from eim.paper.ideas import Idea
from tests.paper.exits.helpers import COSTED, LADDER, coherent_path, ctx
from tests.paper.helpers import M15, T0

DAY = 86_400_000
START = T0 + 30 * DAY
A, B = ab_live.BASE, ab_live.CANDIDATE
FROZEN = Path(eim.__file__).parent / "paper" / "exits" / "versions" / "t135_ab_m8_v1.json"


def _trade(pol: str, iid: str, t: int, r: float, *, sid="s@1h", mae=0.5, exit_t=None,
           risk=100.0) -> BenchTrade:
    return BenchTrade(id=iid, policy=pol, t=t, fill_t=t, exit_t=exit_t or t + 3_600_000, side=1,
                      sid=sid, timeframe="1h", regime="x", origin="o", reason="SL", qty=1.0,
                      risk_usd=risk, pnl_usd=r * risk, gross_usd=r * risk, cost_usd=0.0, r=r,
                      gross_r=r, cost_r=0.1, mfe_r=1.0, mae_r=mae, elapsed_ms=3_600_000)


def _bench(rows: list[tuple[int, float, float]], open_ids=()) -> bench.Bench:
    """(t, R de la base, R de la candidata); la candidata con más riesgo = M8 apartó el SL."""
    out = []
    for k, (t, ra, rb) in enumerate(rows):
        iid = f"i{k}"
        tb = None if iid in open_ids else _trade(B, iid, t, rb, risk=150.0)
        out.append(bench.Row(iid, t, 1.0, {A: _trade(A, iid, t, ra), B: tb},
                             {A: "CERRADA", B: "ABIERTA" if iid in open_ids else "CERRADA"}))
    return bench.Bench(tuple(out), (A, B), 0, {A: {}, B: {"ABIERTA": len(open_ids)}})


def _frozen(**kw) -> dict:
    table = WinnersMae(0, 0.95, 30, {"s@1h": 2.0}, {"s@1h": 40}, 100, 50, "M1 be=1/0.1")
    plan = power.power_plan(B, A, 0.35, 0.05, 200.0, source="prueba")
    args = {"start": START, "cutoff": START - DAY, "plan": plan, "sd_daily": 0.09,
            "t134": {"delta": 0.05}, "pr": load_prereg(), "commit": "abc", "data_note": "copia",
            "mechanics": ab_live.mechanics_of(COSTED, LADDER, ("1h", "4h"))}
    return ab_live.freeze(table, **{**args, **kw})


# --- lo congelado ---------------------------------------------------------------------------------
def test_the_table_cannot_use_data_after_the_start():
    with pytest.raises(ValueError, match="posteriores al inicio"):
        _frozen(cutoff=START + 1)


def test_a_frozen_plan_edited_by_hand_is_refused(tmp_path):
    p = tmp_path / "ab.json"
    ab_live.save_frozen(_frozen(), p)
    assert ab_live.load_frozen(p)["start"] == START
    data = json.loads(p.read_text(encoding="utf-8"))
    data["required_n"] = 1                # bajar el mínimo después de ver datos
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="huella"):
        ab_live.load_frozen(p)


def test_a_frozen_plan_cannot_be_rewritten_with_other_values(tmp_path):
    p = tmp_path / "ab.json"
    ab_live.save_frozen(_frozen(), p)
    ab_live.save_frozen(_frozen(), p)     # el mismo contenido sí
    with pytest.raises(FileExistsError):
        ab_live.save_frozen(_frozen(start=START + DAY), p)


def test_the_published_plan_is_intact_and_says_what_was_agreed():
    """El pre-registro de verdad. Si alguien lo edita, esto falla: cambiarlo es una versión nueva."""
    f = ab_live.load_frozen(FROZEN)
    assert f["candidate"] == "M8 q=0.95" and f["base"] == "M0 first_r=0.1"
    assert f["mode"] == "SIMULADO" and f["start_iso"].startswith("2026-11-08T00:00")
    assert f["fit_cutoff_iso"] < f["start_iso"] and f["min_weeks"] >= 4
    assert f["required_n"] == 315 and f["required_days"] == 21
    assert f["sigma_stop"] == "atr14" and f["sigma_ratio"] == "parkinson"
    assert f["decision_timeframes"] == ["1h", "4h"] and f["table"]["quantile"] == ab_live.QUANTILE


def test_required_days_come_from_the_daily_dispersion():
    f = _frozen()
    assert f["required_days"] == power.required_n(0.09, 0.05)
    assert f["required_n"] == power.required_n(0.35, 0.05)
    assert f["min_weeks"] == power.MIN_WEEKS


def test_fit_table_only_learns_from_trades_closed_before_the_embargo():
    pr, cutoff, emb = load_prereg(), START, 2 * DAY
    n = pr.winners_mae.min_trades
    ok = [_trade("M1", f"a{k}", cutoff - 10 * DAY, 1.0, mae=1.0) for k in range(n)]
    # Cierran dentro del embargo o después, o perdieron: con ellas el cuantil saldría 100.
    late = [_trade("M1", f"b{k}", cutoff - 3 * DAY, 1.0, mae=100.0, exit_t=cutoff - DAY)
            for k in range(n)]
    losers = [_trade("M1", f"c{k}", cutoff - 10 * DAY, -1.0, mae=100.0) for k in range(n)]
    after = [_trade("M1", f"d{k}", cutoff + DAY, 1.0, mae=100.0) for k in range(n)]
    t = ab_live.fit_table([*ok, *late, *losers, *after], lambda _: 1.0, cutoff, emb, pr)
    assert t.quantile == ab_live.QUANTILE and t.of("s@1h") == pytest.approx(1.0)


def test_without_enough_winners_there_is_no_quantile():
    pr = load_prereg()
    few = [_trade("M1", f"a{k}", START - 10 * DAY, 1.0)
           for k in range(pr.winners_mae.min_trades - 1)]
    assert ab_live.fit_table(few, lambda _: 1.0, START, 0, pr).of("s@1h") is None


def test_quantile_of_reads_the_frozen_table():
    of = ab_live.quantile_of(_frozen())
    assert of("s@1h", START) == pytest.approx(2.0) and of("otra@1h", START) is None


def _idea(t: int, tf: str = "1h", strategy: str = "s", side: int = 1) -> Idea:
    return Idea(id=f"{strategy}:{t}:{tf}", strategy=strategy, family="f", symbol="BTCUSDT", t=t,
                side=side, kind="market", entry=70_000.0, sl=69_930.0, tp=70_500.0, fill_ms=0,
                hold_ms=48 * 3_600_000, conf=0.5, why=("t",), timeframe=tf)


def test_only_new_ideas_of_the_t134_universe_count():
    keep = [_idea(START), _idea(START + DAY, "4h")]
    out = [_idea(START - 1), _idea(START, "15m"), _idea(START, strategy=bench.CONTROL_STRATEGY)]
    assert ab_live.counted_ideas([*out, *keep], _frozen()) == keep


def test_pick_fails_instead_of_measuring_something_else():
    with pytest.raises(KeyError):
        ab_live.pick([])


# --- la medida ------------------------------------------------------------------------------------
def test_evaluate_counts_only_what_both_closed():
    b = _bench([(START, -0.2, -0.1), (START + DAY, -0.3, -0.1), (START + 2 * DAY, 0.1, -1.0)],
               open_ids=("i2",))
    ev = ab_live.evaluate(b, _frozen(), START + 7 * DAY)
    assert ev["n"] == 2 and ev["days"] == 2 and ev["ideas"] == 3
    assert ev["delta"] == pytest.approx(0.15) and ev["weeks"] == pytest.approx(1.0)
    assert ev["e_r_candidate"] == pytest.approx(-0.1) and ev["moved_sl"] == 2
    assert ev["dropped"][B] == {"ABIERTA": 1}


def test_the_interval_is_reproducible():
    b = _bench([(START + k * DAY, -0.2, -0.2 + 0.01 * (k % 5)) for k in range(30)])
    f = _frozen()
    assert ab_live.evaluate(b, f, START)["ci"] == ab_live.evaluate(b, f, START)["ci"]


def test_an_empty_ab_does_not_break():
    ev = ab_live.evaluate(bench.Bench((), (A, B), 0, {}), _frozen(), START)
    assert ev["n"] == 0 and ev["delta"] is None
    assert ab_live.verdict(ev, _frozen())["state"] == ab_live.RUNNING
    assert "sin dato" in ab_live.render(ev, _frozen())


# --- el veredicto ---------------------------------------------------------------------------------
def _ev(**kw) -> dict:
    return {"weeks": 6.0, "n": 5000, "days": 300, "delta": 0.05, "ci": [0.01, 0.09], **kw}


def test_a_good_result_too_early_is_not_a_verdict():
    """Cada mínimo por separado: parar en una semana buena sería ajustar el resultado."""
    f = _frozen()
    for early in ({"weeks": f["min_weeks"] - 0.1}, {"n": f["required_n"] - 1},
                  {"days": f["required_days"] - 1}):
        v = ab_live.verdict(_ev(**early), f)
        assert v["state"] == ab_live.RUNNING and "faltan" in v["why"]


def test_it_passes_only_positive_and_with_t134_inside_the_interval():
    f = _frozen()
    assert ab_live.verdict(_ev(), f)["state"] == ab_live.PASS
    assert ab_live.verdict(_ev(delta=-0.01, ci=[-0.05, 0.06]), f)["state"] == ab_live.FAIL
    assert ab_live.verdict(_ev(delta=0.0, ci=[-0.05, 0.06]), f)["state"] == ab_live.FAIL
    degraded = ab_live.verdict(_ev(delta=0.01, ci=[0.001, 0.02]), f)   # positivo, pero degradado
    assert degraded["state"] == ab_live.FAIL and "degradó" in degraded["why"]


def test_a_pass_whose_interval_includes_zero_says_so():
    """El criterio 7 lo deja pasar, y una salida sin efecto lo logra a veces: se tiene que ver."""
    f = _frozen()
    weak = ab_live.verdict(_ev(delta=0.02, ci=[-0.01, 0.06]), f)
    assert weak["state"] == ab_live.PASS and "incluye el 0" in weak["why"]
    assert "incluye el 0" not in ab_live.verdict(_ev(), f)["why"]


def test_the_first_verdict_stands_and_later_weeks_cannot_change_it(tmp_path):
    """Sin esto, un NO PASA se podría convertir en PASA con solo seguir corriendo."""
    f, p = _frozen(), tmp_path / "veredicto.json"
    early = _ev(weeks=1.0)
    assert ab_live.settled(ab_live.verdict(early, f), early, p)["state"] == ab_live.RUNNING
    assert not p.exists()                     # EN CURSO no fija nada
    bad = _ev(delta=-0.01, ci=[-0.05, 0.06], last_iso="semana 4")
    assert ab_live.settled(ab_live.verdict(bad, f), bad, p)["state"] == ab_live.FAIL
    good = _ev(last_iso="semana 7")
    later = ab_live.settled(ab_live.verdict(good, f), good, p)
    assert later["state"] == ab_live.FAIL and later["at"] == "semana 4"


def test_a_verdict_cannot_mix_two_mechanics():
    """Cambiar costos o escalera a mitad de camino es medir otra cosa: no hay veredicto."""
    f = _frozen()
    other = ab_live.mechanics_of(COSTED, LADDER.model_copy(update={"first_r": 0.2}), ("1h", "4h"))
    assert other != f["mechanics"]
    b = _bench([(START, -0.2, -0.1)])
    assert ab_live.evaluate(b, f, START, f["mechanics"])["mechanics_changed"] is False
    ev = ab_live.evaluate(b, f, START, other)
    assert ev["mechanics_changed"] is True
    v = ab_live.verdict({**_ev(), "mechanics_changed": True}, f)
    assert v["state"] == ab_live.RUNNING and "mecánica" in v["why"]


def test_the_report_says_the_mode_and_that_measuring_is_not_adopting():
    f = _frozen()
    running = ab_live.render(_ev(n=10, e_r_base=-0.15, e_r_candidate=-0.1, gross_r_base=0.0,
                                 gross_r_candidate=0.0, cost_r_base=0.15, cost_r_candidate=0.1,
                                 moved_sl=9, ideas=12, dropped={}, last_iso="x"), f, "copia x")
    assert "SIMULADO" in running and "EN CURSO" in running and "No se decide" in running
    assert "no es adoptar" in running.lower() and "copia x" in running


# --- M8 de verdad, con el mismo `grid` que T134 ---------------------------------------------------
@pytest.fixture(scope="module")
def world():
    path, fine = coherent_path(600, 7)
    f = features.build(path, "atr14", swing_bars=5, fine=fine)
    return path, fine, {n: f for n in ab_live.SIGMAS}


def _run(world, of):
    path, fine, feats = world
    vs, _ = grid.expand(load_prereg(), feats, LADDER, path.t,
                        quantile_for=lambda q: of if q == ab_live.QUANTILE else None)
    base, cand = ab_live.pick(vs)
    ideas = [_idea(T0 + (50 + 20 * k) * M15, side=1 if k % 2 else -1) for k in range(15)]
    ideas = [Idea(**{**i.__dict__, "entry": float(path.c[int((i.t - T0) / M15) - 1]),
                     "sl": float(path.c[int((i.t - T0) / M15) - 1]) * (1 - i.side * 0.001),
                     "tp": float(path.c[int((i.t - T0) / M15) - 1]) * (1 + i.side * 0.05)})
             for i in ideas]
    return bench.run(ideas, [base.policy, cand.policy], ctx(path, COSTED, fine), 100.0)


def test_m8_without_a_table_entry_is_the_ladder_itself(world):
    """Las estrategias sin muestra no se tocan: su diferencia con la base es exactamente cero."""
    b = _run(world, lambda sid, t: None)
    assert b.paired() and all(d == 0.0 for _, d in b.diffs(B, A))


def test_m8_with_a_table_entry_moves_the_stop_outwards(world):
    b = _run(world, lambda sid, t: 5.0)
    rows = b.paired()
    assert rows and all(r.by_policy[B].risk_usd >= r.by_policy[A].risk_usd - 1e-6 for r in rows)
    assert any(r.by_policy[B].risk_usd > r.by_policy[A].risk_usd for r in rows)
