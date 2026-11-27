"""Acciones y ETF al contado (T92): comisión por acción, diferencial, préstamo para cortos,
dividendos y splits, **sin apalancamiento implícito**.

- Comisión: por acción con mínimo por orden y máximo como fracción del valor negociado.
- Corto: solo si `shortable`; paga `borrow_rate_annual` sobre el nocional por día natural
  (el préstamo de valores devenga también el fin de semana) y el dividendo íntegro al
  prestamista; el largo cobra el dividendo neto de retención.
- Margen: cuenta de efectivo, `max_leverage = 1`. El corto inmoviliza el 100 % del nocional
  (regla propia, más estricta que Reg T) y su mantenimiento sigue a FINRA 4210.
- Splits y dividendos llegan como eventos (`eim.data.adjust.PriceEvent`) y los aplica el motor
  por instrumento sobre el precio **crudo**: un split no es una pérdida del 75 %.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from eim.backtest.costs.base import (
    DAY_MS,
    ContractKind,
    MarginReq,
    SlippageParams,
    Sourced,
    slippage,
)
from eim.core import Candle

_EQ_SLIP = SlippageParams(spread_bps=2.0, liquidity_notional=5e7)


class EquityCostModel(Sourced):
    version: str = "equity_v1"
    commission_per_share: float = Field(default=0.005, ge=0)
    commission_min: float = Field(default=1.0, ge=0)
    commission_max_frac: float = Field(default=0.01, ge=0)
    slippage: SlippageParams = _EQ_SLIP
    shortable: bool = True
    borrow_rate_annual: float = Field(default=0.0025, ge=0)
    borrow_day_count: float = Field(default=360.0, gt=0)
    dividend_withholding: float = Field(default=0.0, ge=0, lt=1)
    max_leverage: float = Field(default=1.0, ge=1.0, le=4.0)
    short_initial_frac: float = Field(default=1.0, gt=0)
    long_maintenance_frac: float = Field(default=0.25, ge=0, lt=1)
    short_maintenance_frac: float = Field(default=0.30, ge=0, lt=1)

    kind: ClassVar[ContractKind] = ContractKind.EQUITY
    uses_perp_engine: ClassVar[bool] = False
    SOURCES: ClassVar[dict[str, str]] = {
        "version": "T92",
        "commission_per_share": "supuesto: tarifa fija pública de un intermediario minorista "
                                "de EE. UU. (0,005 USD/acción), no verificada en la fuente "
                                "en T92 (no hay intermediario elegido: T103)",
        "commission_min": "supuesto: mínimo por orden de esa misma tarifa (1 USD)",
        "commission_max_frac": "supuesto: máximo del 1 % del valor negociado de esa tarifa",
        "slippage": "supuesto: 2 pb de diferencial en una acción grande y líquida",
        "shortable": "supuesto: disponible para préstamo; la disponibilidad real es por valor "
                     "y por día (sin fuente gratuita, T88)",
        "borrow_rate_annual": "supuesto: 0,25 % anual de un valor de préstamo general; los "
                              "difíciles de prestar pagan mucho más",
        "borrow_day_count": "supuesto: base 360 de la convención del préstamo de valores en USD",
        "dividend_withholding": "supuesto: sin retención (depende del país del inversor)",
        "max_leverage": "regla de T92: sin apalancamiento implícito (cuenta de efectivo)",
        "short_initial_frac": "regla propia: el corto inmoviliza el 100 % del nocional",
        "long_maintenance_frac": "FINRA Rule 4210, 25 % (no verificada en la fuente en T92; "
                                 "sin préstamo no se llega a usar)",
        "short_maintenance_frac": "FINRA Rule 4210, 30 % para valores ≥ 5 USD (no verificada "
                                  "en la fuente en T92)",
    }

    def commission(self, qty: float, price: float, multiplier: float = 1.0, *,
                   maker: bool = False) -> float:
        value = qty * price * multiplier
        if qty <= 0:
            return 0.0
        fee = max(self.commission_min, qty * self.commission_per_share)
        return min(fee, self.commission_max_frac * value) if self.commission_max_frac else fee

    def slippage_frac(self, c: Candle, notional: float, traded: float | None = None, *,
                      entry: bool = False, tick: float | None = None, t: int | None = None
                      ) -> float:
        return slippage(self.slippage, c, notional, traded)

    def financing(self, side: int, notional: float, t0: int, t1: int) -> float:
        """Préstamo de valores del corto, por tiempo natural; el largo al contado no paga."""
        if side >= 0 or t1 <= t0:
            return 0.0
        return abs(notional) * self.borrow_rate_annual * (t1 - t0) / DAY_MS / self.borrow_day_count

    def dividend_cash(self, side: int, qty: float, dividend: float) -> float:
        """Efectivo del dividendo para la posición (+ cobrado): el largo cobra neto de
        retención; el corto paga el importe íntegro (pago sustitutivo al prestamista)."""
        gross = qty * dividend
        return gross * (1 - self.dividend_withholding) if side > 0 else -gross

    def margin(self, side: int, notional: float) -> MarginReq:
        if side < 0:
            return MarginReq(notional * self.short_initial_frac,
                             notional * self.short_maintenance_frac)
        borrowed = max(0.0, 1 - 1 / self.max_leverage)
        return MarginReq(notional / self.max_leverage,
                         notional * self.long_maintenance_frac if borrowed > 0 else 0.0)
