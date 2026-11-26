"""T92: integridad del motor por instrumento — sin anticipación, costos 0 = bruto, dividendo y
split, roll de futuros, swap de FX, cierre de mercado, vencimiento, margen, y regresión de
perpetuos (un perpetuo pasa por el motor de siempre, cifra a cifra)."""
from __future__ import annotations

import pytest

from eim.backtest.class_engine import run_instrument_backtest
from eim.backtest.class_report import annualization, build_class_report, class_cost_breakdown
from eim.backtest.costs import EquityCostModel, FuturesCostModel, FxCostModel, SlippageParams
from eim.backtest.costs.fx import rollovers
from eim.backtest.engine import run_backtest
from eim.backtest.params import BacktestParams
from eim.data.adjust import PriceEvent
from eim.instruments.registry import BTCUSDT
from tests.backtest.t92_helpers import DAY, At, H, equity, future, fx, line, load
from tests.backtest.test_t92_perp_golden import CONFIGS, SmaCross, _inputs

P = BacktestParams(lookback=10_000, max_hold_bars=0, risk_frac=0.01, initial_equity=100_000)
Z_SLIP = SlippageParams(spread_bps=0.0, vol_k=0.0, impact_k=0.0)
Z_EQ = EquityCostModel(commission_per_share=0, commission_min=0, commission_max_frac=0,
                       slippage=Z_SLIP, borrow_rate_annual=0)
Z_FX = FxCostModel(slippage=Z_SLIP, swap_markup_annual=0,
                   spread_bps_by_session=dict.fromkeys(
                       ("asia", "london", "overlap", "new_york", "rollover"), 0.0))
Z_FUT = FuturesCostModel(commission_per_contract=0, slippage=Z_SLIP, spread_ticks=0)


def _identity(res) -> None:
    c = class_cost_breakdown(res)
    assert c["gross_pnl"] - c["total_costs"] + c["dividends"] == pytest.approx(c["net_pnl"])
    assert res.equity[-1] == pytest.approx(P.initial_equity + c["net_pnl"])


# --- sin anticipación ---------------------------------------------------------
def test_no_look_ahead_and_fill_at_next_open():
    cs = line(30, slope=0.5)
    strat = At({5: (1, 0.05, 0.5)})
    res = run_instrument_backtest(cs, strat, equity(), params=P, model=Z_EQ)
    for snap in strat.seen:
        assert snap.candles[-1].t < snap.asof                # decide con velas cerradas
    t = res.trades[0]
    assert t.entry_t == cs[6].t and t.entry_ref == cs[6].o   # apertura de la vela siguiente
    # Mutar el futuro no cambia lo decidido antes
    cs2 = cs[:20] + line(10, p0=1.0, t0=cs[20].t)
    s2 = At({5: (1, 0.05, 0.5)})
    run_instrument_backtest(cs2, s2, equity(), params=P, model=Z_EQ)
    before = [s for s in strat.seen if s.candles[-1].t < cs[20].t]
    assert [s.candles[-1].c for s in s2.seen[:len(before)]] == [s.candles[-1].c for s in before]


# --- costos 0 = bruto ---------------------------------------------------------
@pytest.mark.parametrize("inst,model", [(equity(), Z_EQ), (fx(), Z_FX),
                                        (future(multiplier=10), Z_FUT)],
                         ids=["equity", "fx", "future"])
def test_zero_costs_equal_gross(inst, model):
    cs = line(40, p0=100.0, slope=0.2, step=H if inst.symbol == "EURUSD" else DAY)
    strat = At({3: (1, 0.03, 0.03), 20: (-1, 0.03, 0.03)})
    res = run_instrument_backtest(cs, strat, inst, params=P, model=model)
    assert res.trades
    for t in res.trades:
        assert t.fees == t.slippage == t.financing == t.roll_costs == 0.0
        assert t.net_pnl == pytest.approx(t.gross_pnl)
    _identity(res)


# --- dividendo y split -------------------------------------------------------
def test_split_and_dividend_on_raw_prices():
    d, cs, ev = load("equity_split_dividend")
    res = run_instrument_backtest(cs, At({2: (1, 0.2, 0.5)}), equity(), params=P, model=Z_EQ,
                                  events=ev)
    (t,) = res.trades
    assert res.stats["splits"] == 1 and res.stats["dividends"] == 1
    assert t.reason == "end"                                  # el split NO dispara el SL
    q0 = round(P.initial_equity * P.risk_frac / (cs[2].c * 0.2))
    assert t.qty == pytest.approx(q0 * 4)                     # 4 acciones por cada vieja
    assert t.dividends == pytest.approx(t.qty * 0.5)          # tras el split, 0,50 por acción
    # bruto = variación real de valor: (salida − entrada/4) × 4·q0
    assert t.gross_pnl == pytest.approx((cs[-1].c - cs[3].o / 4) * t.qty)
    _identity(res)


def test_short_pays_dividend_and_borrow():
    _, cs, ev = load("equity_split_dividend")
    m = EquityCostModel(borrow_rate_annual=0.05)
    res = run_instrument_backtest(cs, At({2: (-1, 0.5, 0.9)}), equity(), params=P, model=m,
                                  events=ev)
    (t,) = res.trades
    assert t.dividends == pytest.approx(-t.qty * 0.5)
    days = (t.exit_t - t.entry_t) / DAY
    assert t.financing == pytest.approx(t.qty / 4 * cs[3].o * 0.05 * days / 360, rel=0.05)
    _identity(res)


# --- roll de futuros -----------------------------------------------------------
def test_future_roll_realizes_old_leg_and_charges_roll():
    _, cs, ev = load("future_roll")
    m = FuturesCostModel(commission_per_contract=2.0, slippage=Z_SLIP, spread_ticks=0)
    res = run_instrument_backtest(cs, At({2: (1, 0.01, 0.5)}), future(multiplier=1000),
                                  params=P, model=m, events=ev)
    (t,) = res.trades
    j = next(i for i, c in enumerate(cs) if c.t >= ev[0].t)
    old = cs[j - 1].c
    expected = ((old - cs[3].o) + (cs[-1].c - old * 1.03)) * 1000 * t.qty
    assert t.rolls == 1 and res.stats["rolls"] == 1
    assert t.gross_pnl == pytest.approx(expected)             # el salto del empalme no es PnL
    assert t.roll_costs == pytest.approx(2 * 2.0 * t.qty)     # cerrar viejo + abrir nuevo
    assert t.fees == pytest.approx(2 * 2.0 * t.qty)           # entrada + salida
    _identity(res)


def test_future_expiry_closes_and_blocks_new_entries():
    cs = line(20, p0=70.0, slope=0.01)
    exp = cs[12].t
    res = run_instrument_backtest(cs, At({2: (1, 0.2, 0.5), 11: (1, 0.2, 0.5)}),
                                  future(multiplier=10, expiry=exp), params=P, model=Z_FUT)
    (t,) = res.trades
    assert t.reason == "expiry" and t.exit_t == cs[11].t
    assert res.stats["signals"] == 1                          # tras vencer no decide


# --- swap de FX ----------------------------------------------------------------
def test_fx_swap_over_wednesday_rollover():
    _, cs, _ = load("fx_weekend")
    m = FxCostModel(rate_base_annual=0.02, rate_quote_annual=0.045, swap_markup_annual=0.0,
                    slippage=Z_SLIP, spread_bps_by_session=Z_FX.spread_bps_by_session)
    res = run_instrument_backtest(cs, At({1: (1, 0.05, 0.5)}), fx(), params=P, model=m,
                                  timeframe="1h")
    (t,) = res.trades
    days = sum(n for _, n in rollovers(t.entry_t, t.exit_t))
    assert days >= 1
    assert t.financing == pytest.approx(t.qty * t.entry_ref * 0.025 * days / 365, rel=0.02)
    _identity(res)


# --- cierre de mercado ---------------------------------------------------------
def test_closed_market_waits_and_fills_at_reopen_gap():
    cs = line(12, p0=100.0, slope=0.0, step=H)
    gap = cs[6].model_copy(update={"o": 103.0, "h": 103.5, "l": 102.5, "c": 103.0})
    cs = cs[:6] + [gap] + [c.model_copy(update={"o": 103.0, "h": 103.3, "l": 102.7, "c": 103.0})
                           for c in cs[7:]]
    closed = {cs[3].t, cs[4].t, cs[5].t}
    res = run_instrument_backtest(cs, At({2: (1, 0.05, 0.5)}), equity(), params=P, model=Z_EQ,
                                  is_open=lambda t: t not in closed, timeframe="1h")
    (t,) = res.trades
    assert res.stats["waited_closed"] == 3
    assert t.entry_t == cs[6].t and t.entry_ref == 103.0      # se llena en la reapertura


def test_stop_not_triggered_while_closed():
    cs = line(10, p0=100.0, step=H)
    crash = cs[5].model_copy(update={"l": 80.0})              # fuera de sesión
    cs = cs[:5] + [crash] + cs[6:]
    res = run_instrument_backtest(cs, At({1: (1, 0.05, 0.5)}), equity(), params=P, model=Z_EQ,
                                  is_open=lambda t: t != cs[5].t, timeframe="1h")
    assert res.trades[0].reason == "end"


# --- margen --------------------------------------------------------------------
def test_fx_stop_out_before_wide_stop():
    cs = line(10, p0=1.10, slope=0.0, step=H) + line(5, p0=1.10, slope=-0.02, t0=10 * H, step=H)
    m = Z_FX.model_copy(update={"regulation": "esma_retail"})
    p = P.model_copy(update={"risk_frac": 0.9})            # 30× de nocional: SL a 3 % = −90 %
    res = run_instrument_backtest(cs, At({2: (1, 0.03, 0.5)}), fx(), params=p, model=m,
                                  timeframe="1h")
    assert res.trades[0].reason == "margin"


# --- regresión de perpetuos ----------------------------------------------------
@pytest.mark.parametrize("name", list(CONFIGS))
def test_perpetual_goes_through_the_old_engine_identically(name):
    cs, fund = _inputs()
    a = run_backtest(cs, fund, SmaCross(), CONFIGS[name], symbol="BTCUSDT", timeframe="1h",
                     trade_from=30)
    b = run_instrument_backtest(cs, SmaCross(), BTCUSDT, params=CONFIGS[name], funding=fund,
                                timeframe="1h", trade_from=30)
    assert a.trades_dicts() == b.trades_dicts()
    assert a.equity == b.equity and a.stats == b.stats


# --- informe ---------------------------------------------------------------------
def test_report_breakdown_and_annualization():
    assert annualization(BTCUSDT, "1h") == (8766.0, "calendario 24/7")
    _, cs, ev = load("equity_split_dividend")
    res = run_instrument_backtest(cs, At({2: (1, 0.2, 0.5)}), equity(), params=P, events=ev)
    rep = build_class_report(res, equity(), P, "1d", EquityCostModel(), "fixture T90")
    assert rep["meta"]["cost_model"] == "equity_v1" and rep["meta"]["assumptions"]
    assert rep["costs"]["fees"] > 0 and rep["costs"]["dividends"] > 0
    bpy = rep["meta"]["bars_per_year"]
    if bpy is None:                                           # sin exchange_calendars
        assert rep["metrics"]["sharpe"] is None and "warning_annualization" in rep["metrics"]
    else:
        assert 245 < bpy < 256                                # NYSE en diario, no 8766


def test_dividend_event_is_known_only_from_its_date():
    cs = line(10, p0=50.0)
    ev = [PriceEvent(t=cs[8].t, dividend=1.0)]
    res = run_instrument_backtest(cs, At({1: (1, 0.2, 0.5)}), equity(), params=P, model=Z_EQ,
                                  events=ev)
    assert res.trades[0].dividends == pytest.approx(res.trades[0].qty * 1.0)
    early = run_instrument_backtest(cs[:8], At({1: (1, 0.2, 0.5)}), equity(), params=P,
                                    model=Z_EQ, events=ev)
    assert early.trades[0].dividends == 0.0
