"""Parámetros del agente `liquidations`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LiquidationsParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    stale_days: int = 30  # antigüedad del último archivo a partir de la cual el dato es obsoleto
    lookback_days: int = 7  # ventana (días con datos) del desequilibrio long/short
    min_total_usd: float = 1_000_000.0  # notional mínimo en la ventana para emitir sesgo
    max_confidence: float = 0.5
    top_levels: int = 3  # niveles de precio con más liquidación que se dibujan
    horizon_bars: int = 24
