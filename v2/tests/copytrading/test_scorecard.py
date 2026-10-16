"""Scorecard de líderes (T41): descartes explicados, vigilancia adelante y aprobación."""

from __future__ import annotations

from eim.copytrading import LeaderData, ScoreParams, build_board, score
from eim.copytrading.trades import build_trips
from tests.copytrading.helpers import (
    DAY,
    T0,
    fill,
    leader,
    portfolio,
    position,
    quotes,
    series,
    trip,
)

P = ScoreParams()
NOW = T0 + 11 * DAY


def _data(fills, *, fwd_start=T0, days=10.0, pf=None, q=None, positions=()) -> LeaderData:
    return LeaderData(leader=leader(), fills=fills, positions=list(positions),
                      portfolio=pf if pf is not None else portfolio(120),
                      quotes=quotes(fills) if q is None else q, forward_start=fwd_start,
                      observed_ms=int(days * DAY))


def _consistent(**kw):
    return series(300, T0 + 1000, 10 * DAY, edge=0.002, noise=0.004, **kw)


def _codes(card, kind="descarte"):
    return {r.code for r in card.reasons if r.kind == kind}


def test_lucky_streak_small_sample_is_rejected():
    fills = series(5, T0 + 1000, DAY, edge=0.03, noise=0.001)  # 5 de 5 ganadas, +3 % cada una
    card, _ = score(_data(fills, pf=[]), 100, NOW)
    assert card.all.n == 5 and card.all.win_rate == 1.0
    assert card.verdict == "rejected" and "muestra" in _codes(card)
    assert any("5 operaciones cerradas < 20" in r.text for r in card.reasons)
    assert card.quality == 0


def test_consistent_leader_is_approved():
    fills = _consistent()
    card, fwd = score(_data(fills), 100, NOW)
    assert card.verdict == "approved", card.reasons
    f = card.fwd
    assert f.n == 300 and len(fwd) == 300 and f.dsr >= P.dsr_min
    assert f.mean_ci[0] > 0 and f.sharpe_ci[0] < f.sharpe < f.sharpe_ci[1]
    cp = card.copyability
    assert cp.trades == 300 and 0 < cp.follower_net < cp.leader_net
    assert 0 < card.quality <= f.dsr
    assert _codes(card, "aprobado") == {"aprobado"}


def test_only_history_stays_in_watch():
    fills = _consistent()
    card, _ = score(_data(fills, fwd_start=NOW, days=0.0), 100, NOW)
    assert card.fwd.n == 0 and card.hist.n == 300
    assert card.verdict == "watch" and _codes(card, "vigilancia") == {"adelante"}


def test_short_forward_window_stays_in_watch():
    card, _ = score(_data(_consistent(), days=2.0), 100, NOW)
    assert card.verdict == "watch"
    assert any("2,0/7 d" in r.text for r in card.reasons)


def test_one_trade_explains_profit_is_rejected():
    fills = series(40, T0 + 1000, 9 * DAY, edge=-0.0005, noise=0.001)
    fills += trip("BTC", "long", 0.2, 50_000.0, 55_000.0, T0 + 9 * DAY + 5000, 60_000, 9_000)
    card, _ = score(_data(fills), 100, NOW)
    assert card.verdict == "rejected" and "racha" in _codes(card)


def test_averaging_down_is_rejected():
    fills, t = [], T0 + 1000
    for i in range(30):
        fills += [fill("BTC", 0.0, 0.1, 50_000.0, t, 10 * i + 1),
                  fill("BTC", 0.1, 0.2, 49_000.0, t + 1000, 10 * i + 2),
                  fill("BTC", 0.2, 0.0, 50_500.0, t + 2000, 10 * i + 3, pnl=0.2 * 1_000.0)]
        t += DAY // 4
    card, _ = score(_data(fills), 100, NOW)
    assert card.all.avg_down_share == 1.0
    assert card.verdict == "rejected" and "promediado" in _codes(card)


def test_hidden_latent_losses_are_rejected():
    pos = [position("BTC", "long", 10.0, 60_000.0, NOW - 1000, upnl=-200_000.0)]
    card, _ = score(_data(_consistent(), positions=pos), 100, NOW)
    assert card.unrealized == -200_000.0
    assert card.verdict == "rejected" and "latentes" in _codes(card)


def test_not_copyable_when_follower_loses():
    fills = _consistent()
    card, _ = score(_data(fills, q=quotes(fills, adverse_bps=15.0)), 100, NOW)
    assert card.fwd.dsr >= P.dsr_min  # el líder sí tiene ventaja…
    assert card.verdict == "rejected" and "no_copiable" in _codes(card)  # …el seguidor no
    assert card.copyability.follower_net < 0 < card.copyability.leader_net


def test_losing_portfolio_and_big_drawdown_are_rejected():
    pf = portfolio(120, daily=0.001, dd_at=8, dd=0.6)
    card, _ = score(_data(_consistent(), pf=pf), 100, NOW)
    assert "drawdown" in _codes(card) and card.portfolio.max_dd > 0.5


def test_more_wallets_deflate_more():
    fills = series(120, T0 + 1000, 10 * DAY, edge=0.0012, noise=0.004)
    few, _ = score(_data(fills), 5, NOW)
    many, _ = score(_data(fills), 5000, NOW)
    assert few.fwd.sharpe == many.fwd.sharpe
    assert many.fwd.dsr < few.fwd.dsr and many.fwd.sr0 > few.fwd.sr0
    lo_few, lo_many = few.fwd.mean_ci[0], many.fwd.mean_ci[0]
    assert lo_many < lo_few  # intervalo más ancho con más billeteras


def test_ranking_explains_every_rejection_and_is_deterministic():
    good, _ = score(_data(_consistent()), 100, NOW)
    lucky, _ = score(_data(series(5, T0 + 1000, DAY, 0.03, 0.001), pf=[]), 100, NOW)
    watch, _ = score(_data(_consistent(), days=1.0), 100, NOW)
    b = build_board(NOW, [lucky, watch, good], 100, {}, {}, {}, {}, P.summary())
    assert [c.verdict for c in b.leaders] == ["approved", "watch", "rejected"]
    assert [c.rank for c in b.leaders] == [1, 2, 3]
    assert all(any(r.kind == "descarte" for r in c.reasons)
               for c in b.leaders if c.verdict == "rejected")
    assert [w.leader_id for w in b.weights] == [good.leader_id] and b.weights[0].quality > 0
    again, _ = score(_data(_consistent()), 100, NOW)
    assert again == good


def test_trips_are_net_of_fees_and_funding():
    fills = trip("ETH", "short", 2.0, 2_500.0, 2_400.0, T0, 3_600_000, 1)
    (tr,) = build_trips(fills)
    assert tr.closed and tr.complete and tr.pnl == 200.0
    assert abs(tr.net - (200.0 - tr.fees)) < 1e-9 and tr.fees > 0


def test_short_sample_does_not_judge_streaks():
    fills = series(8, T0 + 1000, 2 * DAY, edge=-0.001, noise=0.001)  # 8 operaciones, 2 días
    fills += trip("BTC", "long", 0.2, 50_000.0, 52_000.0, T0 + 2 * DAY + 5000, 60_000, 9_000)
    card, _ = score(_data(fills, days=2.0), 100, NOW)  # cartera de 120 d: pasa la muestra
    assert card.all.best_trade_share >= 1  # la mejor explica todo… con 9 operaciones
    assert card.verdict == "watch" and not _codes(card)


def test_portfolio_streak_is_rejected():
    t = [T0 - (6 - k) * 7 * DAY for k in range(7)]
    pnl = [0.0, -100.0, -200.0, 5_000.0, 4_900.0, 4_800.0, 4_700.0]  # todo en una semana
    av = [1_000_000.0 + x for x in pnl]
    pts = {"accountValueHistory": [[a, str(b)] for a, b in zip(t, av, strict=True)],
           "pnlHistory": [[a, str(b)] for a, b in zip(t, pnl, strict=True)], "vlm": "1"}
    pf = [["perpAllTime", pts]]
    card, _ = score(_data(_consistent(), pf=pf), 100, NOW)
    assert card.portfolio.best_window == 5_200.0
    assert card.verdict == "rejected" and "racha" in _codes(card)
