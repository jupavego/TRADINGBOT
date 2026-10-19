"""Parámetros del agente `bots` (nada mágico en `agent.py`)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BotsParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Estado de cada bot-estrategia («bot_id@estrategia») en el ciclo de vida que fija T59
    # (observa → vota → degradado…). Lo que no figura está «observa»: se muestra, no vota.
    states: dict[str, str] = Field(default_factory=dict)
    voting_state: str = "vota"
    # Peso de un votante que no declara confianza (el bot no la da; no se inventa una confianza).
    neutral_weight: float = Field(default=1.0, gt=0)
    # Confianza del AGENTE si vota algún bot sin confianza propia: supuesto declarado, bajo, y
    # se avisa en `warnings`. T59 la sustituye por la calibrada.
    fallback_confidence: float = Field(default=0.3, ge=0, le=1)
