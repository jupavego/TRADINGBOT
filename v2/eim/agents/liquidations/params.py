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

    # --- flujo en vivo (recolector multi-bolsa) ---
    min_flow_bars: int = 24  # velas con la recolección viva para emitir algo
    baseline_bars: int = 288  # ventana (velas) que define lo «normal» de liquidación
    recent_bars: int = 3  # velas que cuentan como «ahora»
    exhaust_bars: int = 6  # ventana donde buscar una cascada ya agotada
    z_active: float = 2.0  # z (log-notional) desde el que hay cascada
    z_calm: float = 0.5  # z por debajo del cual la cascada se considera agotada
    z_full: float = 4.0  # z con el que la intensidad llega al máximo
    min_flow_usd: float = 250_000.0  # notional mínimo reciente para hablar de cascada
    momentum_gain: float = 0.6  # sesgo en cascada activa (a favor del flujo forzado)
    reversal_gain: float = 0.4  # sesgo tras agotarse (contra el flujo forzado)
    min_coverage: float = 0.8  # fracción mínima de velas completas en la ventana reciente
    min_venue_usd: float = 50_000.0  # notional mínimo por bolsa para contar en la confirmación
    flow_horizon_bars: int = 6
