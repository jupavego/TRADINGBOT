"""Agente `context`: lectura estructurada de titulares con LLM (solo informa)."""

from eim.agents.context.agent import ContextAgent
from eim.agents.context.params import ContextParams
from eim.agents.context.schema import ContextOutput

__all__ = ["ContextAgent", "ContextOutput", "ContextParams"]
