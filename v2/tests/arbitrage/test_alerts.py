"""Alertas del escáner (T39): umbral sostenido N segundos de escaneos seguidos."""

from __future__ import annotations

from eim.arbitrage import ArbParams, scan_all, select
from eim.arbitrage.alerts import AlertParams, AlertTracker, opp_key
from eim.arbitrage.selector import Selection
from eim.core import CostModel
from tests.arbitrage.helpers import ASOF, book, carry_market, market, perp, quarterly

P = ArbParams(assets=("BTC",))
S = 1000


def _sel(rate: float, t: int) -> Selection:
    mkt = carry_market(rate, realized=rate).model_copy(update={"asof": t})
    return scan_all(mkt, CostModel(), P).selection


def strong(t: int = ASOF) -> Selection:
    """Carry de funding con 0,5 %/8 h escaneado en `t`: muy por encima de 3 pb/día."""
    return _sel(0.005, t)


def weak(t: int = ASOF) -> Selection:
    return _sel(0.0001, t)


def test_alert_fires_after_hold_and_only_once():
    assert strong().selected and strong().selected[0].score >= 3
    tr = AlertTracker(AlertParams(min_score=3, hold_s=60))
    a0, a1, a2, a3 = (tr.update(strong(ASOF + k * S), ASOF + k * S) for k in (0, 30, 60, 90))
    assert [a.active for a in (a0[0], a1[0], a2[0], a3[0])] == [False, False, True, True]
    assert a1[0].held_s == 30 and a2[0].held_s == 60
    assert a2[0].new and not a3[0].new
    assert a3[0].since == ASOF


def test_below_threshold_or_rejected_never_alerts():
    tr = AlertTracker(AlertParams(min_score=3, hold_s=0))
    assert tr.update(weak(), ASOF) == []


def test_dropping_below_threshold_resets_the_count():
    tr = AlertTracker(AlertParams(min_score=3, hold_s=60))
    tr.update(strong(), ASOF)
    tr.update(weak(ASOF + 30 * S), ASOF + 30 * S)
    again = tr.update(strong(ASOF + 60 * S), ASOF + 60 * S)
    assert again[0].since == ASOF + 60 * S and not again[0].active


def test_scanner_gap_resets_and_same_asof_is_idempotent():
    tr = AlertTracker(AlertParams(min_score=3, hold_s=60, max_gap_s=120))
    first = tr.update(strong(), ASOF)
    assert tr.update(strong(), ASOF) is first  # mismo escaneo: no avanza
    after_gap = tr.update(strong(ASOF + 300 * S), ASOF + 300 * S)
    assert after_gap[0].since == ASOF + 300 * S and not after_gap[0].active


def test_expired_quote_does_not_alert():
    sel = strong()
    tr = AlertTracker(AlertParams(min_score=3, hold_s=0))
    late = sel.selected[0].opportunity.valid_until + 1
    assert tr.update(sel, late) == []


def test_opportunity_key_distinguishes_quarterlies():
    q1, q2 = quarterly("BTC", 60), quarterly("BTC", 150)
    q2 = q2.model_copy(update={"symbol": "BTCUSDT_Q2"})
    mkt = market(spot={"BTCUSDT": book(60_000)},
                 futures={"BTCUSDT": book(60_000), q1.symbol: book(60_600),
                          q2.symbol: book(61_200)}, contracts=[perp("BTC"), q1, q2])
    sel = select([o for s in scan_all(mkt, CostModel(), P).scans for o in s.opportunities], P)
    spot_q = [r.opportunity for r in sel.selected + sel.rejected
              if r.opportunity.variant == "largo spot / corto trimestral"]
    assert len(spot_q) == 2
    assert len({opp_key(o) for o in spot_q}) == 2
