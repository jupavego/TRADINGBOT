"""Dimensionamiento y margen por clase (T92): un `Sizer` por tipo de contrato.

- **Perpetuo**: `PerpSizer` llama a `size_position` tal cual (apalancamiento entero con la
  liquidación a ≥ k veces la distancia del SL): BTC/ETH no cambian ni un decimal.
- **Acciones, FX y futuros**: `ClassSizer` sustituye al apalancamiento entero por el margen de
  su clase (efectivo 1×, apalancamiento de la regulación, margen por contrato), convierte a la
  moneda de la cuenta y aplica los topes por contrato y por nocional. El riesgo por operación
  y el tope de nocional siguen saliendo de la misma `RiskConfig` versionada.

`sizer_for(inst)` elige el suyo a partir del registro de instrumentos (T89).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from eim.backtest.costs import ContractKind, CostModel, cost_model_for
from eim.backtest.costs.sizing import FxRate, class_quantity, quote_to_account
from eim.instruments.models import Instrument
from eim.risk.config import RiskConfig
from eim.risk.sizing import Sizing, size_position


class ClassLimits(BaseModel):
    """Topes propios de la clase, además de los de `RiskConfig` (None = sin tope)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_contracts: float | None = Field(default=None, gt=0)
    max_notional: float | None = Field(default=None, gt=0)    # en moneda de la cuenta


@dataclass(frozen=True)
class ClassSizing:
    """Tamaño fuera de perpetuos. `margin_call_price` sustituye al precio de liquidación."""

    size: float                 # acciones, unidades o contratos
    notional: float             # moneda de la cuenta
    leverage: float             # nocional / capital (continuo, no entero)
    margin: float               # inicial, moneda de la cuenta
    risk_amount: float          # moneda de la cuenta
    margin_call_price: float | None
    cost_model: str
    notes: tuple[str, ...]


class Sizer(Protocol):
    def size(self, side: int, entry: float, sl: float, equity: float, cfg: RiskConfig,
             scale: float = 1.0, why: str = "") -> Sizing | ClassSizing | str: ...


class PerpSizer:
    """El dimensionamiento de siempre (`risk/sizing.size_position`)."""

    def size(self, side: int, entry: float, sl: float, equity: float, cfg: RiskConfig,
             scale: float = 1.0, why: str = "") -> Sizing | str:
        return size_position(side, entry, sl, equity, cfg, scale=scale, why=why)


class ClassSizer:
    def __init__(self, inst: Instrument, model: CostModel, fx_rate: FxRate,
                 limits: ClassLimits | None = None) -> None:
        self.inst, self.model, self.fx_rate = inst, model, fx_rate
        self.limits = limits or ClassLimits()

    def size(self, side: int, entry: float, sl: float, equity: float, cfg: RiskConfig,
             scale: float = 1.0, why: str = "", t: int = 0) -> ClassSizing | str:
        rate = self.fx_rate(t, entry)
        q = class_quantity(self.model, self.inst, side, entry, sl, equity,
                           cfg.risk_per_trade * scale, rate,
                           max_notional_frac=cfg.max_notional_frac,
                           max_contracts=self.limits.max_contracts,
                           max_notional=self.limits.max_notional)
        if isinstance(q, str):
            return q
        notes = list(q.notes)
        if scale < 1:
            notes.insert(0, f"tamaño ×{scale:.2f} por {why or 'ventana de evento'}")
        m = self.inst.multiplier
        notional_q = q.qty * entry * m
        if self.model.kind is ContractKind.FUTURE:
            maint = self.model.margin(side, notional_q, q.qty).maintenance
        else:
            maint = self.model.margin(side, notional_q).maintenance
        room = (equity / rate - maint) / (q.qty * m)
        if room <= 0:
            return "el margen de mantenimiento no deja recorrido desde la entrada"
        mc = entry - side * room
        if (sl - mc) * side <= 0:
            return f"el cierre por margen ({mc:,.4f}) llegaría antes que el SL ({sl:,.4f})"
        return ClassSizing(size=q.qty, notional=q.notional, leverage=q.notional / equity,
                           margin=q.margin, risk_amount=q.risk_amount,
                           margin_call_price=mc if mc > 0 else None,
                           cost_model=self.model.version, notes=tuple(notes))


def sizer_for(inst: Instrument, *, model: CostModel | None = None,
              fx_rate: FxRate | None = None, account_currency: str = "USD",
              limits: ClassLimits | None = None) -> PerpSizer | ClassSizer:
    """El `Sizer` del instrumento: perpetuo → el de siempre; el resto → el de su clase."""
    model = model or cost_model_for(inst)
    if model.uses_perp_engine:
        return PerpSizer()
    return ClassSizer(inst, model, fx_rate or quote_to_account(inst, account_currency), limits)
