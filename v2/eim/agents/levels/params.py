"""Parámetros del agente `levels` (sin números mágicos en la lógica)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LevelsParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_bars: int = 60
    atr_period: int = 14
    pivot_n: int = 5                 # velas a cada lado para confirmar un pivote
    # Zonas
    zone_cluster_atr: float = 0.6    # distancia máx. (en ATR) para agrupar pivotes
    zone_min_thickness_atr: float = 0.3
    zone_min_touches: int = 2
    zone_lookback: int = 400         # velas consideradas para pivotes de zona
    recency_half_life: int = 150     # velas: vida media del peso por recencia
    zone_min_rel_score: float = 0.35  # descarta zonas con <35% de la puntuación máxima
    max_zones_per_side: int = 2      # visibles por encima y por debajo del precio
    # Canal / rango
    channel_lookback: int = 160
    channel_min_pivots: int = 2      # por lado (techo y piso)
    channel_touch_atr: float = 0.5   # tolerancia de toque a la línea
    range_drift_ratio: float = 0.35  # |deriva|/ancho por debajo de esto = rango lateral
    min_channel_width_atr: float = 1.0
    break_bars: int = 3              # cierres consecutivos fuera = canal roto
    break_margin_atr: float = 0.1
    extend_bars: int = 30            # proyección hacia adelante (velas)
    # Sesgo
    horizon_bars: int = 24
    max_confidence: float = 0.85
