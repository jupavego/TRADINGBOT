"""Parámetros del agente `arbitrage` (el motor y sus supuestos están en `eim/arbitrage/`)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from eim.arbitrage.params import DEFAULT_PARAMS, ArbParams
from eim.core import CostModel


class ArbAgentParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    engine: ArbParams = DEFAULT_PARAMS  # supuestos del motor T38 (nocional, umbrales, riesgo)
    cost_model: CostModel = CostModel()  # VIP 0 sin BNB por defecto (verificado 2026-10-15)
    top_n: int = Field(default=5, ge=1)  # mejores oportunidades con desglose en `metrics`
    funding_hist_n: int = Field(default=21, ge=1)  # liquidaciones del histórico corto (7 d a 8 h)
    # Frescura: plena hasta la vigencia de un precio de libro, cero a los `stale_s`.
    fresh_s: float = Field(default=15.0, ge=0)
    stale_s: float = Field(default=180.0, gt=0)
    min_book_levels: int = Field(default=20, ge=1)  # niveles por lado para profundidad plena
