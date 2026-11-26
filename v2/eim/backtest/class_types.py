"""Tipos del motor por instrumento (T92): la operación cerrada y la posición viva."""

from __future__ import annotations

from dataclasses import dataclass, replace

from eim.backtest.strategy import Signal

INF = float("inf")


@dataclass
class ClassTrade:
    side: int
    entry_t: int
    exit_t: int
    entry_ref: float          # apertura de ejecución (precio crudo; tras un split, ya ÷ r)
    exit_ref: float
    entry_fill: float
    exit_fill: float
    qty: float                # acciones, unidades o contratos
    reason: str               # sl | tp | margin | time | expiry | end
    sl: float
    tp: float
    gross_pnl: float          # en la moneda de la cuenta, incluidos los tramos ya empalmados
    fees: float
    slippage: float
    financing: float          # + = pagado (préstamo, swap)
    dividends: float          # + = cobrado
    roll_costs: float
    net_pnl: float            # gross − fees − slippage − financing + dividends − roll_costs
    r_multiple: float
    bars: int
    rolls: int = 0
    tag: str = ""


@dataclass
class _Pos:
    sig: Signal
    entry_j: int
    entry_t: int
    entry_ref: float
    entry_fill: float
    qty: float
    margin_px: float
    risk_amt: float
    fees: float
    slippage: float
    last_fin_t: int
    realized: float = 0.0
    financing: float = 0.0
    dividends: float = 0.0
    roll_costs: float = 0.0
    rolls: int = 0


def _scale(sig: Signal, k: float) -> Signal:
    return replace(sig, sl=sig.sl * k, tp=sig.tp * k)
