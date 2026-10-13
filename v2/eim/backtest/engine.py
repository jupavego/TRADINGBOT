"""Motor de backtest de perpetuos, vela a vela y sin anticipación.

Orden dentro de la vela `j`: (a) se ejecuta en su APERTURA la señal decidida al cierre de `j−1`;
(b) funding liquidado en la apertura; (c) salida por tiempo; (d) SL/TP/liquidación intra-vela;
(e) valoración al cierre; (f) si está plano, la estrategia decide con velas `≤ j`.
La estrategia solo ve `candles[:j+1]` y el funding anterior al cierre de `j`.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass, field

import numpy as np

from eim.backtest.params import BacktestParams
from eim.backtest.perp import exit_in_bar, fill, liquidation_price, slippage_frac
from eim.backtest.strategy import Signal, Strategy
from eim.core import Candle, MarketSnapshot


@dataclass
class Trade:
    side: int
    entry_t: int
    exit_t: int
    entry_ref: float          # apertura de la vela de ejecución (sin deslizamiento)
    exit_ref: float           # nivel de salida (sin deslizamiento)
    entry_fill: float
    exit_fill: float
    qty: float
    reason: str               # sl | tp | liq | time | end
    sl: float
    tp: float
    gross_pnl: float          # side·(exit_ref − entry_ref)·qty
    fees: float
    slippage: float
    funding: float            # + = pagado
    liq_fee: float
    net_pnl: float            # gross − fees − slippage − funding − liq_fee
    r_multiple: float         # net_pnl / riesgo inicial en USDT
    bars: int
    tag: str = ""


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_t: list[int]
    equity: list[float]
    stats: dict = field(default_factory=dict)

    def trades_dicts(self) -> list[dict]:
        return [asdict(t) for t in self.trades]


@dataclass
class _Pos:
    sig: Signal
    entry_j: int
    entry_t: int
    entry_ref: float
    entry_fill: float
    qty: float
    liq: float
    margin: float
    risk_usd: float
    fees: float
    slippage: float
    funding: float = 0.0
    last_fund_t: int = 0


def _bar_ms(candles: list[Candle]) -> int:
    return int(np.median(np.diff([c.t for c in candles]))) if len(candles) > 1 else 0


def run_backtest(
    candles: list[Candle],
    funding: list[tuple[int, float]] | None,
    strategy: Strategy,
    params: BacktestParams | None = None,
    symbol: str = "ETHUSDT",
    timeframe: str = "1h",
    trade_from: int = 0,
    sources: dict[str, str] | None = None,
) -> BacktestResult:
    """Simula la estrategia sobre `candles`; solo opera desde la vela `trade_from` (los datos
    anteriores son contexto/calentamiento). Posición abierta al final → se cierra a la última
    apertura con motivo `end`."""
    p = params or BacktestParams()
    cp = p.costs
    n = len(candles)
    step = _bar_ms(candles)
    f_t = [t for t, _ in funding] if funding else []
    f_all = funding or []
    equity = p.initial_equity
    pos: _Pos | None = None
    pending: Signal | None = None
    trades: list[Trade] = []
    eq_t: list[int] = []
    eq: list[float] = []
    st = {"bars_in_position": 0, "signals": 0, "rejected": 0, "funding_expected": 0,
          "funding_observed": 0, "ruined": False}

    def close(j: int, reason: str, ref: float) -> None:
        nonlocal pos, equity
        c, ps = candles[j], pos
        assert ps is not None
        side, notional = ps.sig.side, ps.qty * ps.entry_ref
        slip_x = liq_fee = 0.0
        fee_x = 0.0
        exit_fill = ref
        if reason in ("sl", "time", "end"):
            slip = slippage_frac(c, ps.qty * ref, cp)
            exit_fill = fill(ref, -side, slip)
            slip_x = abs(exit_fill - ref) * ps.qty
            fee_x = cp.taker_fee * ps.qty * exit_fill
        elif reason == "tp":
            fee_x = cp.maker_fee * ps.qty * ref
        gross = side * (ref - ps.entry_ref) * ps.qty
        if reason == "liq":  # se pierde el margen aislado; nunca más (fondo de seguro)
            liq_fee = gross - max(gross - cp.mmr * notional, -ps.margin)
        fees = ps.fees + fee_x
        slippage = ps.slippage + slip_x
        net = gross - fees - slippage - ps.funding - liq_fee
        equity += gross - slippage - fee_x - liq_fee - ps.funding
        trades.append(Trade(
            side=side, entry_t=ps.entry_t, exit_t=c.t, entry_ref=ps.entry_ref, exit_ref=ref,
            entry_fill=ps.entry_fill, exit_fill=exit_fill, qty=ps.qty, reason=reason,
            sl=ps.sig.sl, tp=ps.sig.tp, gross_pnl=gross, fees=fees, slippage=slippage,
            funding=ps.funding, liq_fee=liq_fee, net_pnl=net, r_multiple=net / ps.risk_usd,
            bars=j - ps.entry_j, tag=ps.sig.tag))
        pos = None

    def open_pos(j: int, sig: Signal) -> None:
        nonlocal pos, equity
        c = candles[j]
        ref, side = c.o, sig.side
        if (ref - sig.sl) * side <= 0 or (sig.tp - ref) * side <= 0:
            st["rejected"] += 1       # la apertura ya superó SL o TP
            return
        qty = min(equity * p.risk_frac / abs(ref - sig.sl), equity * p.leverage / ref)
        slip = slippage_frac(c, qty * ref, cp)
        pe = fill(ref, side, slip)
        fee = cp.taker_fee * qty * pe
        equity -= fee
        pos = _Pos(sig=sig, entry_j=j, entry_t=c.t, entry_ref=ref, entry_fill=pe, qty=qty,
                   liq=liquidation_price(side, ref, p.leverage, cp.mmr),
                   margin=qty * ref / p.leverage, risk_usd=equity_risk(qty, ref, sig.sl),
                   fees=fee, slippage=abs(pe - ref) * qty, last_fund_t=c.t)

    def equity_risk(qty: float, ref: float, sl: float) -> float:
        return max(qty * abs(ref - sl), 1e-12)

    for j in range(max(trade_from, 0), n):
        c = candles[j]
        if pending is not None:                                   # (a)
            open_pos(j, pending)
            pending = None
        if pos is not None:
            if j > pos.entry_j:
                st["bars_in_position"] += 1
            lo, hi = bisect_right(f_t, pos.last_fund_t), bisect_right(f_t, c.t)   # (b) funding
            for k in range(lo, hi):
                pos.funding += pos.sig.side * pos.qty * c.o * f_all[k][1]
            iv = cp.funding_interval_ms
            st["funding_expected"] += c.t // iv - pos.last_fund_t // iv
            st["funding_observed"] += hi - lo
            pos.last_fund_t = c.t
            if p.max_hold_bars and j - pos.entry_j >= p.max_hold_bars:          # (c) tiempo
                close(j, "time", c.o)
            else:                                                               # (d) intra-vela
                ex = exit_in_bar(pos.sig.side, pos.sig.sl, pos.sig.tp, pos.liq, c)
                if ex is not None:
                    close(j, ex[0], ex[1])
        if pos is not None and j == n - 1:
            close(j, "end", c.c)
        mark = equity + (pos.sig.side * (c.c - pos.entry_ref) * pos.qty - pos.funding
                         if pos else 0.0)
        eq_t.append(c.t)
        eq.append(mark)                                           # (e)
        if mark <= 0 and pos is None:
            st["ruined"] = True
            break
        if pos is None and j < n - 1 and (j - trade_from) % p.eval_step == 0:   # (f)
            lo_i = max(0, j + 1 - p.lookback)
            fl = None
            if funding:
                fl = f_all[bisect_right(f_t, candles[lo_i].t - 1):bisect_right(f_t, c.t)] or None
            snap = MarketSnapshot(
                symbol=symbol, timeframe=timeframe, candles=candles[lo_i:j + 1], funding=fl,
                asof=c.t + step, sources=sources or {}, coverage={})
            sig = strategy.on_bar(snap)
            if sig is not None:
                st["signals"] += 1
                pending = sig
    st["n_bars"] = len(eq)
    st["final_equity"] = eq[-1] if eq else equity
    return BacktestResult(trades=trades, equity_t=eq_t, equity=eq, stats=st)
