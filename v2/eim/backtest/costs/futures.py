"""Futuros con vencimiento (T92): multiplicador, comisión por contrato, margen inicial y de
mantenimiento, roll y vencimiento.

- El tamaño se cuenta en **contratos enteros**; valor de un punto = `Instrument.multiplier`.
- Comisión por contrato y lado (intermediario + mercado + cámara) y, para plazas que cobran
  sobre nocional (los trimestrales de Binance), `commission_frac`.
- Diferencial en ticks si se conoce el tick del contrato; si no, en puntos básicos.
- Margen por contrato si se fija (lo publica la cámara, p. ej. SPAN de CME); si no, como
  fracción del nocional. El mantenimiento dispara el cierre forzoso (no hay fondo de seguro:
  la pérdida puede pasar del margen en un hueco, como en la realidad).
- Sin financiación aparte: el costo de mantener va dentro del precio (base). Lo que sí cuesta
  es el **roll**: cerrar el contrato que vence y abrir el siguiente, dos comisiones y dos
  medios diferenciales por contrato, `roll_days_before_expiry` días antes del vencimiento.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field, model_validator

from eim.backtest.costs.base import ContractKind, MarginReq, SlippageParams, Sourced, slippage
from eim.core import Candle
from eim.core.fees import USDM_TAKER

_FUT_SLIP = SlippageParams(spread_bps=2.0, liquidity_notional=2e8)


class FuturesCostModel(Sourced):
    version: str = "futures_v1"
    commission_per_contract: float = Field(default=2.25, ge=0)
    commission_frac: float = Field(default=0.0, ge=0)
    slippage: SlippageParams = _FUT_SLIP
    spread_ticks: float = Field(default=1.0, ge=0)
    initial_margin_frac: float = Field(default=0.10, gt=0, le=1)
    maintenance_margin_frac: float = Field(default=0.09, gt=0, le=1)
    initial_margin_per_contract: float | None = Field(default=None, gt=0)
    maintenance_margin_per_contract: float | None = Field(default=None, gt=0)
    roll_days_before_expiry: int = Field(default=5, ge=0)

    @model_validator(mode="after")
    def _coherent(self) -> FuturesCostModel:
        if self.maintenance_margin_frac > self.initial_margin_frac:
            raise ValueError("el mantenimiento no puede superar al margen inicial")
        return self

    kind: ClassVar[ContractKind] = ContractKind.FUTURE
    uses_perp_engine: ClassVar[bool] = False
    SOURCES: ClassVar[dict[str, str]] = {
        "version": "T92",
        "commission_per_contract": "supuesto: 2,25 USD por contrato y lado (intermediario + "
                                   "mercado + cámara) de un futuro estándar de CME; no "
                                   "verificada en la fuente en T92",
        "commission_frac": "supuesto: 0 (solo plazas que cobran sobre nocional la usan)",
        "slippage": "supuesto: 2 pb si no se conoce el tick; impacto con liquidez supuesta",
        "spread_ticks": "supuesto: diferencial de 1 tick en un contrato líquido",
        "initial_margin_frac": "supuesto: 10 % del nocional; el real es por contrato y lo "
                               "publica la cámara (SPAN)",
        "maintenance_margin_frac": "supuesto: 9 % del nocional (90 % del inicial, la proporción "
                                   "habitual en CME)",
        "initial_margin_per_contract": "sin valor por defecto: se fija por contrato con su fuente",
        "maintenance_margin_per_contract": "sin valor por defecto: se fija por contrato",
        "roll_days_before_expiry": "supuesto: roll 5 días antes del vencimiento (antes del "
                                   "aviso de entrega)",
    }

    def commission(self, qty: float, price: float, multiplier: float = 1.0, *,
                   maker: bool = False) -> float:
        return abs(qty) * self.commission_per_contract + \
            self.commission_frac * abs(qty) * price * multiplier

    def slippage_frac(self, c: Candle, notional: float, traded: float | None = None, *,
                      entry: bool = False, tick: float | None = None, t: int | None = None
                      ) -> float:
        spread = (self.spread_ticks * tick / c.o * 1e4) if tick and c.o > 0 else None
        return slippage(self.slippage, c, notional, traded, spread)

    def financing(self, side: int, notional: float, t0: int, t1: int) -> float:
        """Sin financiación aparte: el acarreo va dentro del precio del futuro."""
        return 0.0

    def margin(self, side: int, notional: float, contracts: float | None = None) -> MarginReq:
        n = None if contracts is None else abs(contracts)
        ratio = self.maintenance_margin_frac / self.initial_margin_frac
        if self.initial_margin_per_contract and n is not None:
            init = self.initial_margin_per_contract * n
        else:
            init = notional * self.initial_margin_frac
        if self.maintenance_margin_per_contract and n is not None:
            return MarginReq(init, self.maintenance_margin_per_contract * n)
        return MarginReq(init, init * ratio)

    @property
    def max_leverage(self) -> float:
        """Nocional máximo por unidad de capital que permite el margen inicial."""
        return 1 / self.initial_margin_frac


class BinanceQuarterlyCostModel(FuturesCostModel):
    """Trimestral USDⓈ-M de Binance: cobra sobre nocional como el perpetuo y no tiene funding;
    vence, así que lleva roll. Margen con los valores del perpetuo a falta de los suyos."""

    version: str = "futures_binance_v1"
    commission_per_contract: float = 0.0
    commission_frac: float = USDM_TAKER
    initial_margin_frac: float = 0.05
    maintenance_margin_frac: float = 0.005

    SOURCES: ClassVar[dict[str, str]] = {
        **FuturesCostModel.SOURCES,
        "commission_per_contract": "Binance cobra sobre nocional, no por contrato",
        "commission_frac": "tarifa tomador VIP 0 de USDⓈ-M verificada 2026-10-15 (`eim.core.fees`)",
        "initial_margin_frac": "supuesto: 20× como el tope de riesgo de los perpetuos",
        "maintenance_margin_frac": "mmr del tramo bajo del perpetuo (`CostParams.mmr`); el del "
                                   "trimestral no se verificó",
    }
