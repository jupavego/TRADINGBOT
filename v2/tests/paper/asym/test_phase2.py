"""Fase 2 (T194) y reglas adoptadas (T187): valen desde su instante y no cambian las firmas."""

from __future__ import annotations

from types import SimpleNamespace

from eim.core.authority import params_fingerprint
from eim.paper.asym import prereg as P
from eim.paper.caps import Brake, CapParams, phase2_caps
from eim.paper.catalog import generate_ideas
from eim.paper.ideas import Draft, StrategyInfo
from eim.paper.params import PROFILES, ExecParams
from eim.paper.policy import edge_backed, same_bet
from eim.paper.versioning import exec_fingerprint

T = P.T31_CLOSE_MS


def test_phase2_turns_on_only_from_its_instant():
    p = PROFILES[1].model_copy(update={"phase2_from_ms": T})
    assert not p.costs_in_risk(T - 1) and p.costs_in_risk(T)
    assert p.caps_at(T - 1) is p.caps
    c = p.caps_at(T)
    assert c.dd_steps == P.PHASE2_DD_STEPS and c.dd_brake is None and c.fresh_peak
    assert c.max_dir_risk == p.caps.max_dir_risk           # el tope por dirección sigue
    assert PROFILES[1].caps_at(10**15) is PROFILES[1].caps  # sin instante, nunca


def test_signatures_do_not_change_before_or_after():
    for p in PROFILES:
        q = p.model_copy(update={"phase2_from_ms": T, "asym_from_ms": (("t187b", T),)})
        assert params_fingerprint(q) == params_fingerprint(p)
        assert "fresh_peak" not in p.caps.model_dump()
    ep = ExecParams(phase2_from_ms=T, maker_from_ms=(("15m", T),))
    for tf in ("15m", "1h", "4h"):
        assert exec_fingerprint(ep, tf) == exec_fingerprint(ExecParams(), tf)


def test_gradual_brake_measures_from_its_own_start_and_never_stops():
    caps = phase2_caps(CapParams(max_dir_risk=0.03, dd_brake=0.05))
    b = Brake(peak=10_000.0)                         # la corrida ya cayó antes de encenderlo
    assert b.scale(caps, 7_950.0)[0] == 1.0          # arranca desde el capital de ese momento
    assert b.scale(caps, 7_500.0)[0] == 0.5          # −5,7 %
    assert b.scale(caps, 7_000.0)[0] == 0.25         # −12 %: recorta, no se detiene
    assert b.closed(caps, 7_000.0, 10_000.0, T, -1.0) is None   # sin todo o nada
    b.closed(caps, 8_200.0, 10_000.0, T + 1, 1.0)
    assert b.g_peak == 8_200.0 and b.scale(caps, 8_200.0)[0] == 1.0


def test_brake_of_today_is_untouched_without_phase2():
    caps = CapParams(dd_brake=0.05)
    b = Brake()
    assert b.scale(caps, 9_000.0)[0] == 1.0 and b.g_peak == 0.0
    assert b.closed(caps, 9_000.0, 10_000.0, 0, -1.0) is not None


def _slot(t, side, symbol="BTCUSDT"):
    return SimpleNamespace(o=SimpleNamespace(idea=SimpleNamespace(t=t, symbol=symbol)), side=side)


def test_same_bet_and_edge_helpers():
    st = SimpleNamespace(slots={"a": _slot(5, 1)})
    o = SimpleNamespace(idea=SimpleNamespace(t=5, side=1, symbol="BTCUSDT"))
    assert same_bet(st, o)
    assert not same_bet(st, SimpleNamespace(idea=SimpleNamespace(t=5, side=-1, symbol="BTCUSDT")))
    assert not same_bet(st, SimpleNamespace(idea=SimpleNamespace(t=6, side=1, symbol="BTCUSDT")))
    assert edge_backed(SimpleNamespace(n=25, m=0.2, se=0.05))
    assert not edge_backed(SimpleNamespace(n=25, m=0.04, se=0.05))
    assert not edge_backed(SimpleNamespace(n=10, m=0.5, se=0.01))
    assert not edge_backed(SimpleNamespace(n=30, m=0.5, se=float("nan")))


def _always_long(ctx, _ind, _i):
    c = float(ctx["close"])
    return Draft(side=1, sl=c - 1.0, tp=c + 2.0, conf=0.5, why=("prueba",))


def test_adopted_maker_converts_only_later_ideas():
    info = StrategyInfo("prueba_larga", "Prueba", "agentes", "siempre largo", _always_long)
    ctxs = [{"t": 1_000 + k * 900_000, "close": 100.0 + k} for k in range(4)]
    since = ctxs[2]["t"]
    ep = ExecParams(maker_from_ms=(("15m", since),))
    ideas = generate_ideas(ctxs, [], "BTCUSDT", 900_000, catalog={info.id: info},
                           timeframe="15m", exec_params=ep, maker_entry=True)
    assert [i.kind for i in ideas] == ["market", "market", "limit", "limit"]
    other = generate_ideas(ctxs, [], "BTCUSDT", 900_000, catalog={info.id: info},
                           timeframe="1h", exec_params=ep, maker_entry=True)
    assert {i.kind for i in other} == {"market"}
