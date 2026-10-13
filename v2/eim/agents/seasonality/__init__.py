"""Agente `seasonality`: matriz Año×Mes de retornos y sesgo del mes en curso."""

from eim.agents.seasonality.agent import SeasonalityAgent
from eim.agents.seasonality.params import SeasonalityParams

__all__ = ["SeasonalityAgent", "SeasonalityParams"]
