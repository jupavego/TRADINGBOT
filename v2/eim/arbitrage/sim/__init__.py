"""Simulación y backtest del arbitraje con costos reales (T43): reproduce el motor T38 sobre
el histórico y simula cada oportunidad hasta su salida. Puro sobre `ArbHistory` (el I/O vive
en `eim/data/arb_history*.py`). Modo ANÁLISIS: no envía órdenes."""

from eim.arbitrage.sim.depth import DepthModel, DepthProfile
from eim.arbitrage.sim.frame import ArbHistory, AssetHistory, Bars, Funding, Quarterly
from eim.arbitrage.sim.params import SimParams
from eim.arbitrage.sim.trade import SimTrade

__all__ = ["ArbHistory", "AssetHistory", "Bars", "DepthModel", "DepthProfile", "Funding",
           "Quarterly", "SimParams", "SimTrade"]
