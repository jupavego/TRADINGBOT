"""T92: libro de papel por instrumento — sesiones y costos de su clase; un perpetuo da
exactamente lo mismo que `simulate`."""
from __future__ import annotations

import pytest

from eim.backtest.costs import EquityCostModel, FxCostModel
from eim.instruments.registry import BTCUSDT
from eim.paper.engine import Path, simulate
from eim.paper.ideas import Idea
from eim.paper.instrument_book import session_path, simulate_instrument
from eim.paper.params import ExecParams
from tests.backtest.t92_helpers import H, equity, fx, line

M15 = 15 * 60_000


def _idea(t: int, side: int = 1, entry: float = 100.0, sl: float = 98.0, tp: float = 104.0,
          kind: str = "market", hold_h: int = 48, symbol: str = "ACME") -> Idea:
    return Idea(id="i", strategy="s", family="agentes", symbol=symbol, t=t, side=side, kind=kind,
                entry=entry, sl=sl, tp=tp, fill_ms=4 * H, hold_ms=hold_h * H, conf=0.5,
                why=("prueba",), timeframe="1h")


def test_perpetual_is_simulate_unchanged():
    cs = line(200, p0=100.0, slope=0.05, step=M15)
    path = Path(cs, [(cs[0].t + 8 * H, 0.0001)], M15)
    for idea in (_idea(cs[3].t), _idea(cs[3].t, side=-1, sl=103.0, tp=95.0),
                 _idea(cs[3].t, kind="limit", entry=100.1)):
        assert simulate_instrument(idea, path, BTCUSDT) == simulate(idea, path, ExecParams())


def test_equity_costs_of_its_class():
    cs = line(80, p0=100.0, slope=0.1, step=H)
    path = session_path(cs, H)
    o = simulate_instrument(_idea(cs[2].t), path, equity(), notional=10_000)
    assert o.status == "CERRADA" and o.reason == "TP"
    qty = 10_000 / o.fill
    assert o.fee_in == pytest.approx(EquityCostModel().commission(qty, o.fill) / 10_000)
    assert o.funding == 0.0                                  # largo al contado: sin financiación
    assert o.r == pytest.approx(o.net / o.risk)
    short = simulate_instrument(_idea(cs[2].t, side=-1, sl=130.0, tp=60.0), path, equity(),
                                model=EquityCostModel(borrow_rate_annual=0.10))
    assert short.funding > 0                                 # el corto paga el préstamo


def test_idea_born_while_closed_fills_at_reopen():
    cs = line(30, p0=100.0, step=H)
    closed = {c.t for c in cs[5:9]}
    path = session_path(cs, H, is_open=lambda t: t not in closed)
    o = simulate_instrument(_idea(cs[6].t), path, equity())
    assert o.fill_t == cs[9].t                               # primera vela abierta


def test_fx_swap_charged_in_the_paper_book():
    cs = line(24 * 6, p0=1.10, slope=0.0, step=H, t0=1767571200000)   # lunes 5-ene-2026
    path = session_path(cs, H)
    m = FxCostModel(rate_quote_annual=0.05, swap_markup_annual=0.0)
    o = simulate_instrument(_idea(cs[1].t, entry=1.10, sl=1.0, tp=1.3, hold_h=72, symbol="EURUSD"),
                            path, fx(), model=m)
    assert o.status == "CERRADA" and o.reason == "TIEMPO"
    assert o.funding == pytest.approx(0.05 * 5 / 365, rel=1e-6)   # lun, mar, mié ×3
