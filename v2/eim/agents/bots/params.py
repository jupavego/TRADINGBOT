"""Parámetros del agente `bots` (nada mágico en `agent.py`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from eim.synthesis.squad import SquadPolicy


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
    # T60 (los fija la política de la síntesis, `eim.synthesis.squad`, desde la puntuación de T59):
    # peso medido por bot-estrategia, clase de la ficha, bots cuyo acuerdo modula la confianza y
    # símbolo en que se midió el aporte (en otro, los bots informan pero no votan).
    weights: dict[str, float] = Field(default_factory=dict)
    classes: dict[str, str] = Field(default_factory=dict)
    modulating: frozenset[str] = frozenset()
    vote_symbol: str | None = None


def params_of(policy: SquadPolicy | None) -> BotsParams:
    """Parámetros del agente desde la política del escuadrón (T60); sin política, todos observan."""
    if policy is None or not policy.bots:
        return BotsParams()
    return BotsParams(
        states={b.key: b.state for b in policy.bots},
        weights={b.key: b.weight for b in policy.voters},
        classes={b.key: b.bot_class for b in policy.bots},
        modulating=policy.modulating, vote_symbol=policy.symbol or None)
