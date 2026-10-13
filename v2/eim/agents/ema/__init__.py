"""Agente `ema`: análisis de EMAs (9/21/55/100/200) con las 44 variables del FRM."""

from eim.agents.ema.agent import EMAAgent
from eim.agents.ema.params import EMAParams

__all__ = ["EMAAgent", "EMAParams"]
