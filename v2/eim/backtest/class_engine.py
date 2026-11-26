"""Motor de backtest sobre `Instrument` (T92): acciones, FX y futuros con sus reglas reales.

Mismas reglas conservadoras que el motor de perpetuos (T25, `engine.py`): la señal decidida
al cierre de `j−1` se ejecuta en la APERTURA de `j` con deslizamiento; SL antes que TP en la
misma vela; un hueco más allá del nivel se llena a la apertura; la estrategia solo ve velas
`≤ j`. Lo que añade, en este orden dentro de la vela `j`:

0. **Eventos** con fecha ex en (`t_{j−1}`, `t_j`]: split (cantidad × r, niveles ÷ r), dividendo
   (efectivo según el lado) y empalme de futuro (se realiza el contrato viejo al último cierre,
   se abre el nuevo a ese precio × razón y se cobra el roll). También ajustan la orden pendiente.
1. **Sesiones**: con el mercado cerrado no se ejecuta nada (ni entrada, ni stop, ni tiempo);
   la orden espera a la primera vela abierta y se llena a su apertura (el hueco de apertura).
2. **Financiación** de su clase (préstamo del corto, swap de FX) entre velas.
3. **Margen**: cierre forzoso cuando el capital cae al mantenimiento (`margin`), en vez de la
   liquidación aislada del perpetuo; **vencimiento**: un futuro sin empalme se cierra al último
   cierre antes de vencer (`expiry`) y no se abre nada que venza antes de ejecutarse.

Todo importe del informe va en la moneda de la cuenta (`fx_rate`). **Un perpetuo no pasa por
aquí**: `run_instrument_backtest` le cede el paso entero a `run_backtest`, así BTC/ETH dan
exactamente las mismas cifras que antes de T92 (golden en `tests/backtest/`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from eim.backtest.class_types import INF, ClassTrade, _Pos, _scale
from eim.backtest.costs import CostModel, cost_model_for
from eim.backtest.costs.base import ContractKind
from eim.backtest.costs.sizing import FxRate, class_quantity, quote_to_account
from eim.backtest.engine import BacktestResult, _bar_ms, run_backtest
from eim.backtest.params import BacktestParams
from eim.backtest.perp import exit_in_bar, fill
from eim.backtest.strategy import Signal, Strategy
from eim.core import Candle, MarketSnapshot
from eim.instruments.models import DataCapability, Instrument

if TYPE_CHECKING:   # solo el tipo: el motor no importa la capa de datos
    from eim.data.adjust import PriceEvent


def run_instrument_backtest(
    candles: list[Candle], strategy: Strategy, instrument: Instrument, *,
    params: BacktestParams | None = None, model: CostModel | None = None,
    funding: list[tuple[int, float]] | None = None, events: Sequence[PriceEvent] = (),
    is_open: Callable[[int], bool] | None = None, fx_rate: FxRate | None = None,
    account_currency: str = "USD", timeframe: str = "1d", trade_from: int = 0,
    sources: dict[str, str] | None = None,
) -> BacktestResult:
    """Backtest de `strategy` sobre velas CRUDAS de `instrument` con los costos de su clase.

    `events`: splits, dividendos y empalmes (`eim.data.adjust.PriceEvent`) conocidos.
    `is_open(t)`: ¿abre el mercado en `t`? (None = toda vela recibida está en sesión, que es
    lo que guarda el almacén). `fx_rate`: cotización → cuenta (por defecto, `quote_to_account`).
    """
    explicit = model is not None
    model = model or cost_model_for(instrument)
    p = params or BacktestParams()
    if model.uses_perp_engine:
        if explicit and model.params != p.costs:   # un modelo explícito manda sobre `params`
            p = p.model_copy(update={"costs": model.params})
        return run_backtest(candles, funding, strategy, p, symbol=instrument.symbol,
                            timeframe=timeframe, trade_from=trade_from, sources=sources)
    fx = fx_rate or quote_to_account(instrument, account_currency)
    return _run(candles, strategy, instrument, p, model, sorted(events, key=lambda e: e.t),
                is_open, fx, timeframe, trade_from, sources or {})


def _run(candles, strategy, inst, p, model, events, is_open, fx, timeframe, trade_from,
         sources) -> BacktestResult:
    n, step, m = len(candles), _bar_ms(candles), inst.multiplier
    real_vol = inst.has(DataCapability.REAL_VOLUME)
    equity = p.initial_equity
    pos: _Pos | None = None
    pending: Signal | None = None
    trades: list[ClassTrade] = []
    eq_t: list[int] = []
    eq: list[float] = []
    st = {"bars_in_position": 0, "signals": 0, "rejected": 0, "vetoed": 0, "waited_closed": 0,
          "splits": 0, "dividends": 0, "rolls": 0, "ruined": False}
    veto_reasons: list[str] = []

    def traded(c: Candle) -> float | None:
        return c.v * c.o * m if real_vol and c.v > 0 else None

    def slip(c: Candle, qty: float, px: float, entry: bool = False) -> float:
        return model.slippage_frac(c, qty * px * m, traded(c), entry=entry, tick=inst.tick)

    def close(j: int, reason: str, ref: float) -> None:
        nonlocal pos, equity
        c, ps = candles[j], pos
        assert ps is not None
        side, rate = ps.sig.side, fx(c.t, ref)
        exit_fill, slip_x = ref, 0.0
        if reason == "tp":
            fee_x = model.commission(ps.qty, ref, m, maker=True) * rate
        else:
            exit_fill = fill(ref, -side, slip(c, ps.qty, ref))
            slip_x = abs(exit_fill - ref) * ps.qty * m * rate
            fee_x = model.commission(ps.qty, exit_fill, m) * rate
        leg = side * (ref - ps.entry_ref) * ps.qty * m * rate
        equity += leg - slip_x - fee_x - ps.slippage     # el de entrada se paga al cerrar (T25)
        gross = ps.realized + leg
        fees, slp = ps.fees + fee_x, ps.slippage + slip_x
        net = gross - fees - slp - ps.financing + ps.dividends - ps.roll_costs
        trades.append(ClassTrade(
            side=side, entry_t=ps.entry_t, exit_t=c.t, entry_ref=ps.entry_ref, exit_ref=ref,
            entry_fill=ps.entry_fill, exit_fill=exit_fill, qty=ps.qty, reason=reason,
            sl=ps.sig.sl, tp=ps.sig.tp, gross_pnl=gross, fees=fees, slippage=slp,
            financing=ps.financing, dividends=ps.dividends, roll_costs=ps.roll_costs,
            net_pnl=net, r_multiple=net / ps.risk_amt, bars=j - ps.entry_j, rolls=ps.rolls,
            tag=ps.sig.tag))
        pos = None

    def open_pos(j: int, sig: Signal) -> None:
        nonlocal pos, equity
        c = candles[j]
        ref, side, rate = c.o, sig.side, fx(c.t, c.o)
        if (ref - sig.sl) * side <= 0 or (sig.tp - ref) * side <= 0:
            st["rejected"] += 1       # la apertura (o el hueco) ya superó SL o TP
            return
        q = class_quantity(model, inst, side, ref, sig.sl, equity, p.risk_frac, rate)
        if isinstance(q, str):
            st["vetoed"] += 1
            veto_reasons.append(q)
            return
        level = margin_level(side, ref, q.qty, equity - model.commission(q.qty, ref, m) * rate,
                             rate)
        if level is None:
            st["vetoed"] += 1
            veto_reasons.append("el margen de mantenimiento no deja recorrido")
            return
        pe = fill(ref, side, slip(c, q.qty, ref, entry=True))
        fee = model.commission(q.qty, pe, m) * rate
        equity -= fee
        pos = _Pos(sig=sig, entry_j=j, entry_t=c.t, entry_ref=ref, entry_fill=pe, qty=q.qty,
                   margin_px=level, risk_amt=max(q.risk_amount, 1e-12), fees=fee,
                   slippage=abs(pe - ref) * q.qty * m * rate, last_fin_t=c.t)

    def margin_level(side: int, ref: float, qty: float, eq_acct: float, rate: float
                     ) -> float | None:
        """Precio del cierre forzoso: donde el capital cae al margen de mantenimiento. None si
        no hay recorrido; −∞ si un largo no llega nunca (cuenta de efectivo)."""
        notional_q = qty * ref * m
        mreq = (model.margin(side, notional_q, qty) if model.kind is ContractKind.FUTURE
                else model.margin(side, notional_q))
        room = (eq_acct / rate - mreq.maintenance) / (qty * m)
        if room <= 0:
            return None
        level = ref - side * room
        return -INF if side > 0 and level <= 0 else level

    def apply_events(j: int) -> None:
        nonlocal pending, equity
        c = candles[j]
        lo = candles[j - 1].t if j > 0 else c.t - step
        for e in events:
            if not lo < e.t <= c.t:
                continue
            if e.split:
                st["splits"] += 1
                pending = _scale(pending, 1 / e.split) if pending else None
                if pos:
                    pos.qty *= e.split
                    pos.entry_ref /= e.split
                    pos.entry_fill /= e.split
                    pos.margin_px /= e.split
                    pos.sig = _scale(pos.sig, 1 / e.split)
            if e.dividend and pos and hasattr(model, "dividend_cash"):
                st["dividends"] += 1
                cash = model.dividend_cash(pos.sig.side, pos.qty, e.dividend) * fx(c.t, c.o)
                pos.dividends += cash
                equity += cash
            if e.roll:
                pending = _scale(pending, e.roll) if pending else None
                if pos and j > 0:
                    roll(j, e.roll)

    def roll(j: int, ratio: float) -> None:
        nonlocal equity
        ps, prev = pos, candles[j - 1]
        assert ps is not None
        old, rate = prev.c, fx(prev.t, prev.c)
        leg = ps.sig.side * (old - ps.entry_ref) * ps.qty * m * rate
        cost = (2 * model.commission(ps.qty, old, m) + 2 * slip(prev, ps.qty, old) * ps.qty
                * old * m) * rate
        ps.realized += leg
        ps.roll_costs += cost
        equity += leg - cost
        ps.entry_ref = old * ratio
        level = margin_level(ps.sig.side, ps.entry_ref, ps.qty, equity, rate)
        ps.margin_px = ps.entry_ref if level is None else level
        ps.sig = _scale(ps.sig, ratio)
        ps.rolls += 1
        st["rolls"] += 1

    for j in range(max(trade_from, 0), n):
        c = candles[j]
        apply_events(j)
        open_now = is_open(c.t) if is_open else True
        dead = inst.expiry is not None and c.t >= inst.expiry
        if pending is not None:
            if dead:
                pending = None
            elif not open_now:
                st["waited_closed"] += 1
            else:
                open_pos(j, pending)
                pending = None
        if pos is not None:
            if j > pos.entry_j:
                st["bars_in_position"] += 1
            fin = model.financing(pos.sig.side, pos.qty * c.o * m, pos.last_fin_t, c.t)
            if fin:
                fin *= fx(c.t, c.o)
                pos.financing += fin
                equity -= fin
            pos.last_fin_t = c.t
            if open_now:
                if p.max_hold_bars and j - pos.entry_j >= p.max_hold_bars:
                    close(j, "time", c.o)
                else:
                    ex = exit_in_bar(pos.sig.side, pos.sig.sl, pos.sig.tp, pos.margin_px, c)
                    if ex is not None:
                        close(j, "margin" if ex[0] == "liq" else ex[0], ex[1])
        if pos is not None and inst.expiry is not None and c.t + step >= inst.expiry:
            close(j, "expiry", c.c)
        if pos is not None and j == n - 1:
            close(j, "end", c.c)
        mark = equity + (pos.sig.side * (c.c - pos.entry_ref) * pos.qty * m * fx(c.t, c.c)
                         if pos else 0.0)
        eq_t.append(c.t)
        eq.append(mark)
        if mark <= 0 and pos is None:
            st["ruined"] = True
            break
        expiring = inst.expiry is not None and c.t + 2 * step >= inst.expiry
        if (pos is None and pending is None and j < n - 1 and not expiring
                and (j - trade_from) % p.eval_step == 0):
            lo_i = max(0, j + 1 - p.lookback)
            snap = MarketSnapshot(symbol=inst.symbol, timeframe=timeframe,
                                  candles=candles[lo_i:j + 1], asof=c.t + step,
                                  sources=sources, coverage={})
            sig = strategy.on_bar(snap)
            if sig is not None:
                st["signals"] += 1
                pending = sig
    st["n_bars"] = len(eq)
    st["final_equity"] = eq[-1] if eq else equity
    st["veto_reasons"] = sorted(set(veto_reasons))
    st["cost_model"] = {"version": model.version, "kind": model.kind.value,
                        "fingerprint": model.fingerprint()}
    return BacktestResult(trades=trades, equity_t=eq_t, equity=eq, stats=st)
