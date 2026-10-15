"""Agente `arbitrage` (T39): oportunidades netas de Binance, neutral al mercado (bias 0)."""

from eim.agents.arbitrage.agent import LABEL, ArbitrageAgent
from eim.agents.arbitrage.params import ArbAgentParams

__all__ = ["LABEL", "ArbAgentParams", "ArbitrageAgent"]
