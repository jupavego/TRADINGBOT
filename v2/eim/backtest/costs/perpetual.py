"""Perpetuo lineal USDⓈ-M (T92): el modelo de siempre, envuelto **sin cambiar una cifra**.

`CostParams` (`eim/backtest/params.py`) sigue siendo la fuente de los números y el motor de
perpetuos (`eim/backtest/engine.py`) sigue siendo el que corre BTC/ETH: el motor por
instrumento le cede el paso entero a un perpetuo (`class_engine.run_instrument_backtest`).
Este envoltorio solo expone el contrato común de T92 para el dimensionamiento, el bróker
simulado y los informes que comparan clases.
"""

from __future__ import annotations

from typing import ClassVar

from eim.backtest.costs.base import ContractKind, MarginReq, Sourced
from eim.backtest.params import CostParams
from eim.backtest.perp import slippage_frac
from eim.core import Candle


class PerpCostModel(Sourced):
    version: str = "perp_v1"
    params: CostParams = CostParams()
    max_leverage: float = 20.0

    kind: ClassVar[ContractKind] = ContractKind.PERPETUAL
    uses_perp_engine: ClassVar[bool] = True
    SOURCES: ClassVar[dict[str, str]] = {
        "version": "T92",
        "params": "T25/T143: `CostParams`, tarifa VIP 0 de Binance USDⓈ-M verificada "
                  "2026-10-15 (`eim.core.fees`), mmr del tramo bajo",
        "max_leverage": "tope de `RiskConfig.max_leverage` (≤ 20); el apalancamiento entero "
                        "de cada operación lo decide `risk/sizing.max_safe_leverage`",
    }

    def commission(self, qty: float, price: float, multiplier: float = 1.0, *,
                   maker: bool = False) -> float:
        rate = self.params.maker_fee if maker else self.params.taker_fee
        return rate * qty * price * multiplier

    def slippage_frac(self, c: Candle, notional: float, traded: float | None = None, *,
                      entry: bool = False, tick: float | None = None, t: int | None = None
                      ) -> float:
        return slippage_frac(c, notional, self.params)

    def financing(self, side: int, notional: float, t0: int, t1: int) -> float:
        """El funding lo liquida el motor de perpetuos con las tasas reales del almacén."""
        return 0.0

    def margin(self, side: int, notional: float) -> MarginReq:
        return MarginReq(notional / self.max_leverage, self.params.mmr * notional)
