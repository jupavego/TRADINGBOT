"""Tamaño por clase fuera de perpetuos (T92): riesgo fijo hasta el SL, con multiplicador,
lote, divisa de la cuenta y tope de nocional/margen. Lo comparten el motor por instrumento y
el `Sizer` de riesgo (`eim/risk/sizers.py`); el perpetuo sigue con el apalancamiento entero
de `risk/sizing.py`, intacto.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import NamedTuple

from eim.backtest.costs.base import ContractKind
from eim.instruments.models import Instrument

FxRate = Callable[[int, float], float]
"""Tasa de la moneda de cotización a la de la cuenta en el instante `t` con precio `px`."""


class Quantity(NamedTuple):
    qty: float                 # acciones, unidades de divisa o contratos (ya redondeado)
    notional: float            # en moneda de la cuenta
    margin: float              # inicial, en moneda de la cuenta
    risk_amount: float         # pérdida hasta el SL, en moneda de la cuenta
    notes: tuple[str, ...]


def quote_to_account(inst: Instrument, account_ccy: str) -> FxRate:
    """Conversión por defecto: 1 si cotiza en la moneda de la cuenta; 1/precio si la cuenta es
    la divisa BASE del par (USDJPY con cuenta en USD). En otro caso hace falta una serie de
    cambio y se dice en vez de suponer 1."""
    acct, quote = account_ccy.upper(), inst.quote_currency.upper()
    if quote == acct:
        return lambda _t, _px: 1.0
    if inst.symbol.upper().startswith(acct) and inst.symbol.upper().endswith(quote):
        return lambda _t, px: 1.0 / px if px > 0 else 0.0
    raise ValueError(f"{inst.id} cotiza en {quote} y la cuenta es {acct}: pase `fx_rate` con "
                     f"la serie {quote}{acct} (no se supone 1)")


def round_qty(inst: Instrument, kind: ContractKind, qty: float) -> float:
    """Contratos enteros en futuros; en lo demás, múltiplo del lote si la ficha lo trae."""
    if kind is ContractKind.FUTURE:
        return float(math.floor(qty + 1e-9))
    lot = inst.lot
    return round(math.floor(qty / lot + 1e-9) * lot, 10) if lot else qty


def class_quantity(model, inst: Instrument, side: int, entry: float, sl: float,
                   equity: float, risk_frac: float, fx: float,
                   max_notional_frac: float | None = None, max_contracts: float | None = None,
                   max_notional: float | None = None) -> Quantity | str:
    """Tamaño o motivo (str) de veto. `equity` y los topes en moneda de la cuenta."""
    kind, m = model.kind, inst.multiplier
    if kind is ContractKind.EQUITY and side < 0 and not model.shortable:
        return f"{inst.symbol}: sin acciones disponibles para préstamo (corto no permitido)"
    unit_risk = abs(entry - sl) * m * fx
    if unit_risk <= 0 or entry <= 0 or fx <= 0:
        return "SL en la entrada o precio/cambio no válidos"
    notes: list[str] = []
    qty = equity * risk_frac / unit_risk
    unit_notional = entry * m * fx
    caps = [equity * model.max_leverage]
    if max_notional_frac is not None:
        caps.append(equity * max_notional_frac)
    if max_notional is not None:
        caps.append(max_notional)
    cap = min(caps)
    if qty * unit_notional > cap:
        notes.append(f"tamaño recortado por tope de nocional ({qty * unit_notional:,.0f} → "
                     f"{cap:,.0f})")
        qty = cap / unit_notional
    if kind is ContractKind.FUTURE and model.initial_margin_per_contract:
        by_margin = equity / (model.initial_margin_per_contract * fx)
        if qty > by_margin:
            notes.append(f"recortado por margen por contrato ({qty:.2f} → {by_margin:.2f})")
            qty = by_margin
    if max_contracts is not None and qty > max_contracts:
        notes.append(f"recortado por tope de contratos ({qty:.2f} → {max_contracts:g})")
        qty = float(max_contracts)
    qty = round_qty(inst, kind, qty)
    if qty <= 0:
        unit = "contrato" if kind is ContractKind.FUTURE else "lote"
        return f"el riesgo permitido no alcanza para 1 {unit} de {inst.symbol}"
    notional = qty * unit_notional
    if kind is ContractKind.FUTURE:
        margin = model.margin(side, notional / fx, qty).initial * fx
    else:
        margin = model.margin(side, notional / fx).initial * fx
    return Quantity(qty, notional, margin, qty * unit_risk, tuple(notes))
