"""Viajes de plano a plano, estadística deflactada, copiabilidad, cohortes y cartera (T41)."""

from __future__ import annotations

import math

from eim.copytrading import ScoreParams
from eim.copytrading import stats as S
from eim.copytrading.copyability import copy_stats
from eim.copytrading.forward import VerdictMark, cohorts, covered_ms
from eim.copytrading.portfolio import _returns, portfolio_stats
from eim.copytrading.trades import build_trips
from eim.core.leaders import LeaderFunding
from tests.copytrading.helpers import LID, T0, fill, portfolio, quotes, trip

P = ScoreParams()


def test_flip_closes_and_opens_with_fee_split():
    fills = [fill("BTC", 0.0, 1.0, 100.0, T0, 1, fee=1.0),
             fill("BTC", 1.0, -3.0, 110.0, T0 + 10, 2, pnl=10.0, fee=4.0),
             fill("BTC", -3.0, 0.0, 105.0, T0 + 20, 3, pnl=15.0, fee=3.0)]
    a, b = build_trips(fills)
    assert (a.side, b.side) == ("long", "short") and a.closed and b.closed
    assert a.pnl == 10.0 and math.isclose(a.fees, 1.0 + 1.0)  # 1/4 de la comisión del giro
    assert b.pnl == 15.0 and math.isclose(b.fees, 3.0 + 3.0) and b.size_max == 3.0
    assert b.entry == 110.0 and b.exit == 105.0


def test_position_before_history_is_partial_and_excluded():
    fills = [fill("ETH", 2.0, 1.0, 2_000.0, T0, 1, pnl=50.0),
             fill("ETH", 1.0, 0.0, 2_010.0, T0 + 5, 2, pnl=30.0)]
    (tr,) = build_trips(fills)
    assert tr.closed and not tr.complete and tr.before_history


def test_same_millisecond_follows_position_chain_not_tid():
    fills = [fill("BTC", 0.0, 1.0, 100.0, T0, 1),
             fill("BTC", 1.5, 2.0, 101.0, T0 + 5, 2),  # tid menor, pero va después en la cadena
             fill("BTC", 1.0, 1.5, 101.0, T0 + 5, 3),
             fill("BTC", 2.0, 0.0, 102.0, T0 + 9, 4, pnl=3.5)]
    (tr,) = build_trips(fills)
    assert tr.complete and tr.closed and tr.size_max == 2.0


def test_gap_in_position_chain_marks_trip_incomplete():
    fills = [fill("BTC", 0.0, 1.0, 100.0, T0, 1),
             fill("BTC", 3.0, 0.0, 99.0, T0 + 9, 2, pnl=-3.0)]  # faltan ejecuciones 1 → 3
    trips = build_trips(fills)
    assert [t.complete for t in trips] == [False, False]


def test_funding_goes_to_the_open_trip_and_avg_down_is_counted():
    fills = [fill("BTC", 0.0, 1.0, 100.0, T0, 1),
             fill("BTC", 1.0, 2.0, 95.0, T0 + 3_600_000, 2),  # aumenta un 5 % por debajo
             fill("BTC", 2.0, 0.0, 99.0, T0 + 7_200_000, 3, pnl=-3.0)]
    fund = [LeaderFunding(leader_id=LID, address=LID.split(":")[1], symbol="BTC", usdc=-1.5,
                          rate=1e-4, size=2.0, t=T0 + 5_000_000, observed_at=T0 + 5_000_100,
                          source="test"),
            LeaderFunding(leader_id=LID, address=LID.split(":")[1], symbol="BTC", usdc=-9.0,
                          rate=1e-4, size=0.0, t=T0 + 9_000_000, observed_at=T0, source="test")]
    (tr,) = build_trips(fills, fund)
    assert tr.funding == -1.5 and tr.avg_downs == 1 and tr.net == -3.0 - 1.5


def test_deflated_sharpe_and_bonferroni_widen_with_trials():
    xs = [0.01 * ((i * 7) % 11 - 4.5) + 0.004 for i in range(200)]
    assert S.expected_max_z(1) == 0 < S.expected_max_z(10) < S.expected_max_z(1000)
    d1, d2 = S.deflated(xs, 10), S.deflated(xs, 1000)
    assert d1[0] > d2[0] and d1[1] < d2[1]
    lo1, hi1 = S.sharpe_ci(xs, 0.95, 1)
    lo2, hi2 = S.sharpe_ci(xs, 0.95, 100)
    assert lo2 < lo1 < hi1 < hi2
    assert S.max_drawdown([10, -30, 5], 100.0) == 30 / 110


def test_copy_uses_ask_to_buy_bid_to_sell_and_ignores_stale_quotes():
    fills = trip("BTC", "long", 1.0, 100.0, 101.0, T0, 60_000, 1, fee_rate=0.0)
    trips = build_trips(fills)
    q = quotes(fills, adverse_bps=10.0)
    cp = copy_stats(trips, fills, q, P)
    assert cp.trades == 1 and math.isclose(cp.slip_bps["p50"], 10.0, rel_tol=1e-6)
    assert cp.leader_net == 1.0 and cp.follower_net < 1.0
    assert cp.latency_ms["p50"] == 200 and cp.retention is not None
    old = {k: v.model_copy(update={"quote_t": v.follow_at - 60_000}) for k, v in q.items()}
    assert copy_stats(trips, fills, old, P).trades == 0  # cotización vieja: no vale


def test_cohorts_use_verdict_in_force_at_open():
    fills = (trip("BTC", "long", 1.0, 100.0, 102.0, T0 + 10, 5, 1)
             + trip("BTC", "long", 1.0, 100.0, 99.0, T0 + 100, 5, 3))
    trips = build_trips(fills)
    marks = [VerdictMark(leader_id=LID, t=T0, verdict="watch"),
             VerdictMark(leader_id=LID, t=T0 + 50, verdict="approved")]
    co = cohorts(marks, {LID: trips})
    assert co["watch"].trades == 1 and co["watch"].net > 0
    assert co["approved"].trades == 1 and co["approved"].net < 0
    assert co["rejected"].trades == 0 and co["watch"].since == T0
    assert covered_ms([0, 60_000, 10 * 3_600_000], 900_000) == 60_000 + 900_000


def test_portfolio_returns_ignore_deposits():
    av = [(0, 10_000.0), (1, 110_000.0)]  # +100 000 depositados, +0 de PnL
    pnl = [(0, 0.0), (1, 0.0)]
    assert _returns(av, pnl, 1_000.0) == [0.0]
    st = portfolio_stats(portfolio(70, daily=0.001), P)
    assert st.days == 70 and st.twr > 0 and st.max_dd == 0 and st.windows == 10
    assert portfolio_stats([], P) is None
