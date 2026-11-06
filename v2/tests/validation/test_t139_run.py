"""T139 de punta a punta sobre un mercado sintético, sin red: reglas, puerta, lectura y parada."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from eim.core import Candle
from eim.data.timeframes import STORE_ONLY_TF_MS, TF_MS, tf_ms
from eim.paper.catalog import CATALOG
from eim.validation.attempts import load_attempts, write_attempts
from eim.validation.criteria import load_criteria
from eim.validation.evidence import Trade
from eim.validation.gate import OBSERVACION, Check, Measure, Verdict
from eim.validation.hypotheses import decision as dc
from eim.validation.hypotheses import nulls as nl
from eim.validation.hypotheses import pipeline as pp
from eim.validation.hypotheses import report as rp
from eim.validation.hypotheses import rules as ru
from eim.validation.hypotheses import world as wd
from eim.validation.hypotheses.prereg import load_prereg
from eim.validation.lineage import Version, iso_ms

PR = load_prereg()
CRIT = load_criteria()
EP = ru.exec_params(PR)
M = 60_000
T0 = iso_ms("2022-01-01T00:00:00Z")
DAYS = 130


def _candle(a: np.ndarray, flow: np.ndarray, step: int, i: int, k: int, t0: int) -> Candle:
    seg = a[i:i + k]
    return Candle(t=t0 + i * step, o=float(seg[0]), h=float(seg.max() * 1.0005),
                  l=float(seg.min() * 0.9995), c=float(seg[-1]), v=float(k),
                  taker_buy_v=float(k) * float(flow[i]), trades=k)


@pytest.fixture(scope="module")
def world() -> wd.World:
    """130 días de paseo aleatorio: no hay ventaja que encontrar."""
    rng = np.random.default_rng(139)
    n = DAYS * 24 * 4
    px = 30000 * np.exp(np.cumsum(rng.normal(0, 0.0012, n)))
    flow = np.clip(rng.normal(0.5, 0.12, n), 0.05, 0.95)     # compra agresora, ruido sin más
    fifteen = [_candle(px, flow, 15 * M, i, 1, T0) for i in range(n)]
    bars = {"15m": fifteen}
    for tf, k in (("1h", 4), ("4h", 16)):
        bars[tf] = [_candle(px, flow, 15 * M, i, k, T0) for i in range(0, n - k + 1, k)]
        step = tf_ms(tf)
        bars[tf] = [c.model_copy(update={"t": T0 + j * step}) for j, c in enumerate(bars[tf])]
    funding = [(T0 + 8 * 3_600_000 * j, float(rng.normal(1e-4, 1e-4))) for j in range(DAYS * 3)]
    nm = DAYS * 1440
    mp = 30000 * np.exp(np.cumsum(rng.normal(0, 0.0003, nm)))
    r = rng.uniform(1e-4, 5e-4, nm)
    mins = ru.Minutes(T0 + np.arange(nm, dtype=np.int64) * M, mp.copy(), mp * (1 + r), mp * (1 - r),
                      mp * (1 + rng.normal(0, 1e-4, nm)), rng.lognormal(0, 1, nm))
    return wd.world_of("BTCUSDT", bars, funding, mins)


def _prior() -> dict:
    return {f"BTCUSDT|previa{k}@1h@v1": None for k in range(832)}


@pytest.fixture(scope="module")
def ideas(world):
    return wd.key_ideas(PR, world, EP)


# --- reglas -------------------------------------------------------------------------------------
def test_every_rule_fires_and_uses_the_control_exit(ideas):
    assert set(ideas) == set(PR.sids())
    for sid in ("funding_contra@1h", "flujo_sigue@1h", "flujo_sigue@4h", "momento_1d@1d"):
        assert ideas[sid], sid
    for sid, xs in ideas.items():
        tf = sid.split("@")[1]
        for i in xs[:5]:
            risk, reward = abs(i.entry - i.sl), abs(i.tp - i.entry)
            assert reward / risk == pytest.approx(2.5 / 1.5, rel=1e-6)
            assert i.kind == "market" and i.family == ru.FAMILY and i.timeframe == tf
            assert i.hold_ms == int(24 * tf_ms(tf))
            assert i.version == ru.fingerprint(PR, sid, EP)


def test_flow_rule_is_silent_during_the_warm_up(world, ideas):
    s = world.series["1h"]
    first = min(i.t for i in ideas["flujo_sigue@1h"])
    assert first >= int(s.t[0]) + 90 * 86_400_000


def test_hypotheses_never_enter_the_live_catalog_or_are_imported_by_paper():
    assert not {h.strategy for h in PR.hypotheses} & set(CATALOG)
    root = Path(__file__).resolve().parents[2] / "eim" / "paper"
    for f in root.rglob("*.py"):
        assert "validation.hypotheses" not in f.read_text(encoding="utf-8"), f


def test_daily_timeframe_is_store_only():
    """La API sigue sin exponer 1 d: solo existe para que la sombra de H5 sepa cuánto dura."""
    assert tf_ms("1d") == 86_400_000 and "1d" in STORE_ONLY_TF_MS and "1d" not in TF_MS


def test_be_plus_is_extended_to_1d_without_changing_1h_and_4h():
    from eim.paper.params import ExecParams
    from eim.paper.versioning import exec_fingerprint
    assert "1d" in EP.be_timeframes and "1d" not in ExecParams().be_timeframes
    for tf in ("1h", "4h"):
        assert exec_fingerprint(EP, tf) == exec_fingerprint(ExecParams(), tf)
    assert exec_fingerprint(EP, "1d")["be"] is not None


def test_live_origin_only_from_the_alta():
    alta = iso_ms(PR.live_rule.alta)
    of = ru.origin_rule(alta)
    assert of({"t": alta - 1}) == "backtest" and of({"t": alta}) == "vivo"


def test_unknown_rule_fails_instead_of_staying_silent(world):
    h = PR.hypotheses[0].model_copy(update={"strategy": "otra"})
    with pytest.raises(ValueError, match="desconocida"):
        ru.sides_for(h, world.series["1h"], world.funding, world.minutes)


# --- familia, puerta y registro -------------------------------------------------------------------
def test_family_is_841_and_every_key_counts_even_without_trades():
    versions, family = wd.setup(PR, EP, _prior(), "BTCUSDT")
    assert len(versions) == 9 and len(family) == 841
    assert all(f"BTCUSDT|{v.label}" in family for v in versions)
    with pytest.raises(ValueError, match="familia"):
        wd.setup(PR, EP, {}, "BTCUSDT")


def test_versions_are_retired_and_declare_the_adjust_window():
    v = ru.version_of(PR, "funding_contra@1h", EP)
    assert v.retired_ms == iso_ms(PR.live_rule.alta) and v.parent is None and v.origin == "T139"
    w = v.windows[0]
    t2022, t2024, live = iso_ms("2022-06-01"), iso_ms("2024-06-01"), iso_ms(PR.live_rule.alta)
    assert not w.covers(t2022, "BTCUSDT") and w.covers(t2024, "BTCUSDT")
    assert not w.covers(live, "BTCUSDT")


def test_attempts_folder_gathers_every_file(tmp_path):
    vs = [ru.version_of(PR, sid, EP) for sid in PR.sids()]
    write_attempts(tmp_path / "attempts_t139.json", PR.version, PR.sha256, vs,
                   {v.label: v.strategy for v in vs}, task="T139")
    got = load_attempts(tmp_path)
    assert [v.label for v in got] == sorted(v.label for v in vs) or len(got) == 9
    assert all(x.note.startswith("T139") and x.retired_ms is not None for x in got)
    assert all(not x.windows[0].covers(iso_ms("2021-01-01"), "BTCUSDT") for x in got)


def test_official_reading_counts_before_2023_and_live_but_not_the_bank():
    v = ru.version_of(PR, "funding_contra@1h", EP)
    alta = iso_ms(PR.live_rule.alta)
    ts = [Trade(t=t, exit_t=t + 1, r=0.5, r_flip=-0.5, cost_r=0.1, regime="range",
                origin="backtest") for t in (iso_ms("2022-06-01"), iso_ms("2024-06-01"), alta + 1)]
    official = pp.selected(PR.reading("oficial"), v, ts, "BTCUSDT", alta + 10)
    bank = pp.selected(PR.reading("banco"), v, ts, "BTCUSDT", alta + 10)
    assert [t.t for t in official] == [ts[0].t, ts[2].t]
    assert [t.t for t in bank] == [ts[1].t]


# --- bruto por lado -----------------------------------------------------------------------------
def _t(r: float, cost: float, side: int) -> Trade:
    return Trade(t=0, exit_t=1, r=r, r_flip=-r, cost_r=cost, regime="x", origin="backtest",
                 side=side)


def test_balanced_gross_cancels_the_drift():
    """Con deriva, los largos ganan lo que los cortos pierden: sin habilidad, equilibrado 0."""
    ts = [_t(0.5 - 0.1, 0.1, 1)] * 90 + [_t(-0.5 - 0.1, 0.1, -1)] * 30
    s = pp.side_stats(ts, 20, 1.5)
    assert s.gross == pytest.approx(0.25)
    assert s.balanced == pytest.approx(0.0)
    assert s.stressed == pytest.approx(0.15 - 0.05)
    assert pp.side_stats(ts[:100], 20, 1.5).balanced is None      # un lado casi vacío
    assert pp.side_stats([], 20, 1.5).gross is None


# --- regla de lectura y parada --------------------------------------------------------------------
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
    assert dc.recommend([bad], True, [True])["code"] == "P1"
    assert dc.recommend([good, bad], True, [True])["follow"] == ["a@1h@v1"]
    assert dc.recommend([bad, watch], True, [True])["code"] == "OBSERVACION"
    assert dc.recommend([good, bad], True, [True])["code"] == "SIGUE"
    assert dc.recommend([good], False, [True])["code"] == "P0"
    assert dc.recommend([good], True, [False])["code"] == "CONTROL"


# --- de punta a punta -----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def clean(world):
    pr = PR.model_copy(update={"control": PR.control.model_copy(update={"surrogates": 4,
                                                                        "bars": 1500})})
    return wd.clean_stage(pr, CRIT, world, EP, _prior(), True, lambda _m: None)


def test_end_to_end_on_a_random_walk_nothing_follows(clean):
    assert clean["family"] == 841
    assert len(clean["rows"]) == 9
    assert clean["recommendation"]["code"] in ("P1", "OBSERVACION", "CONTROL")
    assert not clean["recommendation"]["follow"]
    assert all(r["verdict"] != "VALIDADA" for r in clean["rows"])
    assert all(r["reading"] == "oficial" and "state" in r for r in clean["rows"])
    assert set(clean["baseline"]) == {"indicadores", "base", "control"}


def test_report_renders_and_says_the_mode(clean, tmp_path):
    res = {**clean, "meta": {"symbol": "BTCUSDT", "asof": "x", "prereg": PR.version,
                             "prereg_sha256": PR.sha256, "prereg_commit": "3d396f7",
                             "criteria": "validation_v1", "commit": "abc", "family": 841,
                             "null_reps": 33640}}
    md = rp.render_clean(res)
    assert "SIMULADO" in md and "## 1. Recomendación" in md and "funding_contra@1h" in md
    assert rp.gross_needed(1000, 0.15) == pytest.approx(0.212, abs=1e-3)
    assert rp.gross_needed(100, 0.08) == pytest.approx(0.385, abs=1e-3)
    assert rp.gross_needed(0, 0.08) is None


def test_gross_on_a_random_walk_without_costs_is_about_zero(world, ideas):
    """Sobre un paseo aleatorio y sin costos ninguna regla puede dar bruto: si lo da, hay fuga."""
    free = EP.model_copy(update={"costs": EP.costs.model_copy(update={
        "taker_fee": 0.0, "maker_fee": 0.0, "slip_base_bps": 0.0, "slip_vol_k": 0.0,
        "slip_entry_base_bps": 0.0, "slip_entry_vol_k": 0.0})})
    for sid in ("flujo_sigue@1h", "funding_contra@1h"):
        xs = ideas[sid]
        out = [o for o in pp.run_shadow(xs, world.path, free) if o.status == "CERRADA"]
        if len(out) < 20:
            continue
        g = np.array([o.r + (o.fee_in + o.fee_out + o.slip + o.funding) / o.risk for o in out])
        assert abs(g.mean()) < 3.5 * g.std(ddof=1) / np.sqrt(len(g)), sid


def test_regression_compares_against_t137_with_both_paths(world):
    s = world.series["1h"]
    rows = [c for c in ru.minimal_ctxs(s) if c["atr"]][:400]
    got = nl.regression(rows, s, world.path, EP, PR)
    assert got["contexts"] == 400 and got["missing_bars"] == 0
    assert got["atr_rel_diff_max"] == pytest.approx(0.0, abs=1e-12)
    assert got["stored"]["n"] == got["minimal"]["n"]
    assert got["stored"]["ok"] is False      # sobre datos de juguete no puede coincidir con T137


def test_ideas_carry_no_future(world):
    """Reescribir el futuro no cambia ninguna decisión ya tomada, en ninguna regla."""
    s = world.series["1h"]
    cut = int(len(s.t) * 0.8)
    h = PR.hypothesis("flujo_sigue")
    base = ru.sides_for(h, s, world.funding, world.minutes)
    tampered = replace(s, taker=np.where(np.arange(len(s.t)) > cut, s.v, s.taker))
    assert (ru.sides_for(h, tampered, world.funding, world.minutes)[:cut + 1]
            == base[:cut + 1]).all()
    h1 = PR.hypothesis("funding_contra")
    cut_t = int(s.close_t[cut])
    base1 = ru.sides_for(h1, s, world.funding, world.minutes)
    late = [(t, x if t <= cut_t else 1.0) for t, x in world.funding]
    assert (ru.sides_for(h1, s, late, world.minutes)[:cut + 1] == base1[:cut + 1]).all()
    h4 = PR.hypothesis("cascada_revierte")
    m = world.minutes
    base4 = ru.sides_for(h4, s, world.funding, m)
    mask = m.t >= int(s.close_t[cut])
    m2 = replace(m, h=np.where(mask, m.h * 5, m.h), v=np.where(mask, m.v * 50, m.v))
    assert (ru.sides_for(h4, s, world.funding, m2)[:cut + 1] == base4[:cut + 1]).all()
