"""Parámetros de la síntesis (pesos ajustables en T26; sin números mágicos en la lógica)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SynthesisParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Peso base por agente (1.0 si no figura). Calibrable en T26.
    weights: dict[str, float] = Field(default_factory=dict)
    # Agentes que no votan: `plan` deriva de structure/levels (doble conteo) y los no
    # direccionales emiten bias=0 (T44).
    excluded: frozenset[str] = frozenset({"plan", "calendar", "arbitrage", "regime"})
    # Multiplicadores de peso por régimen y agente (cuando exista el agente de régimen, T22).
    regime_weights: dict[str, dict[str, float]] = Field(default_factory=dict)
    degraded_factor: float = 0.5      # un agente degradado pesa y confía la mitad
    conflict_bias: float = 0.2        # |sesgo| mínimo para considerar que un agente toma partido
    disagree_penalty: float = 0.5     # factor de confianza si hay agentes fuertes opuestos
    neutral_band: float = 0.1         # |sesgo| bajo esta banda se describe como neutral
    drift_scale: float = 0.1          # deriva = sesgo·confianza·scale·σ (σ = desv. del log-retorno)
