"""Modelo de costos y de márgenes por clase de activo (T92).

`contract_kind(inst)` decide cómo se cobra un instrumento del registro (T89) y
`cost_model_for(inst)` devuelve su modelo por defecto, versionado y con la fuente de cada
parámetro. La clase la dice el **contrato**, no el subyacente: un perpetuo de Binance sobre
oro o sobre una acción se cobra como perpetuo (funding, liquidación aislada), y BTC/ETH
reciben exactamente el `CostParams` de siempre.
"""

from __future__ import annotations

from eim.backtest.costs.base import (
    ContractKind,
    MarginReq,
    NotTradable,
    SlippageParams,
    Sourced,
    slippage,
)
from eim.backtest.costs.equity import EquityCostModel
from eim.backtest.costs.futures import BinanceQuarterlyCostModel, FuturesCostModel
from eim.backtest.costs.fx import FxCostModel
from eim.backtest.costs.perpetual import PerpCostModel
from eim.instruments.models import AssetClass, Instrument, MarketStructure

CostModel = PerpCostModel | EquityCostModel | FxCostModel | FuturesCostModel
"""Cualquiera de los modelos (BinanceQuarterlyCostModel es un FuturesCostModel)."""

__all__ = [
    "BinanceQuarterlyCostModel", "ContractKind", "CostModel", "EquityCostModel",
    "FuturesCostModel", "FxCostModel",
    "MarginReq", "NotTradable", "PerpCostModel", "SlippageParams", "Sourced",
    "contract_kind", "cost_model_for", "slippage",
]

_OUT_OF_SCOPE = {AssetClass.OPTION, AssetClass.BOND, AssetClass.CASH}


def _binance_usdm(inst: Instrument) -> bool:
    return inst.venue == "binance" and ".usdm." in inst.id


def contract_kind(inst: Instrument) -> ContractKind:
    """Cómo se cobra el instrumento. Levanta `NotTradable` si no se negocia como tal."""
    if inst.market_structure is MarketStructure.SYNTHETIC or inst.asset_class is AssetClass.INDEX:
        raise NotTradable(f"{inst.id}: un índice se calcula, no se negocia (use su ETF o su "
                          "futuro)")
    if inst.asset_class in _OUT_OF_SCOPE:
        raise NotTradable(f"{inst.id}: clase {inst.asset_class.value} fuera de T92 (T100)")
    if _binance_usdm(inst):
        return ContractKind.PERPETUAL if inst.expiry is None else ContractKind.FUTURE
    if inst.expiry is not None or inst.asset_class in (AssetClass.FUTURE, AssetClass.COMMODITY):
        return ContractKind.FUTURE
    if inst.asset_class is AssetClass.FX:
        return ContractKind.FX
    if inst.asset_class in (AssetClass.EQUITY, AssetClass.ETF):
        return ContractKind.EQUITY
    raise NotTradable(f"{inst.id}: clase {inst.asset_class.value} sin modelo de costos")


def cost_model_for(inst: Instrument) -> CostModel:
    """Modelo por defecto del instrumento (los parámetros marcados «supuesto» se sustituyen
    por los medidos en cada clase: T97 acciones, T98 FX, T99 futuros)."""
    kind = contract_kind(inst)
    if kind is ContractKind.PERPETUAL:
        return PerpCostModel()
    if kind is ContractKind.EQUITY:
        return EquityCostModel()
    if kind is ContractKind.FX:
        return FxCostModel(pair=inst.symbol.replace("/", "").upper())
    if _binance_usdm(inst):    # trimestral de Binance: cobra sobre nocional, sin funding
        return BinanceQuarterlyCostModel()
    return FuturesCostModel()
