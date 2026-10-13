"""Parámetros del agente `seasonality`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SeasonalityParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_months: int = 2  # cierres mensuales mínimos para construir la matriz
    min_samples: int = 3  # años con retorno en el mes objetivo para emitir sesgo
    bias_scale_pct: float = 10.0  # retorno medio (%) que equivale a sesgo ±1
    max_confidence: float = 0.4  # tope: la estacionalidad es contexto débil
    horizon_bars: int = 30
    strict_gaps: bool = True  # hueco de meses → retorno NaN (el legado F7 lo interpolaba)
