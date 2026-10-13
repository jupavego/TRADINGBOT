"""Parámetros del agente `derivatives`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DerivativesParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    change_bars: int = 12  # ventana (barras) del cambio de precio y de OI
    min_oi_points: int = 40  # puntos mínimos de OI para el z-score del cambio
    min_funding_points: int = 20  # liquidaciones de funding mínimas para su z-score
    min_series_points: int = 20  # mínimo para long/short y basis (opcionales)
    z_high: float = 1.0  # |z| que cuenta como extremo (funding, L/S, basis)
    z_oi: float = 0.5  # |z| del cambio de OI que cuenta como apertura/cierre
    price_move: float = 0.002  # |retorno| mínimo para considerar que el precio se movió
    max_stale_bars: int = 3  # antigüedad máxima (barras) del último dato de OI
    crowded_bias: float = 0.5  # magnitud del sesgo en apalancamiento saturado
    trend_bias: float = 0.3  # tendencia con OI y funding sanos
    weak_bias: float = 0.15  # cobertura de cortos (rally débil)
    modifier_bias: float = 0.1  # ajuste contrarian por long/short o basis extremos
    max_confidence: float = 0.7
    horizon_bars: int = 12
