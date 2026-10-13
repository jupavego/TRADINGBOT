"""Parámetros del agente `ema` (el cálculo FRM usa `FRMParams` del agente structure)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from eim.agents.structure.params import FRMParams

# Las 44 variables FRM por bloque (orden de cálculo del Apéndice A de EIM-FRM-001).
GROUPS: dict[str, tuple[str, ...]] = {
    "emas": ("EMA_9", "EMA_21", "EMA_55", "EMA_100", "EMA_200"),
    "stack": ("STACK_ORDER", "STACK_SCORE", "PRICE_VS_STACK"),
    "slopes": ("SLOPE_9", "SLOPE_21", "SLOPE_55", "SLOPE_100", "SLOPE_200",
               "SLOPE_DIRECTION", "SLOPE_SYNC"),
    "spreads": ("SPREAD_9_21", "SPREAD_21_55", "SPREAD_55_100", "SPREAD_100_200",
                "COMPRESSION_INDEX", "COMPRESSION_DURATION", "SPREAD_VELOCITY",
                "SPREAD_ACCELERATION"),
    "dynamics": ("ELASTICITY", "VOLUME_RATIO", "ATR_RELATIVE", "CURVATURE_9", "CURVATURE_55",
                 "PERSISTENCE_ABOVE_21"),
    "bounces": ("BOUNCE_COUNT_9", "BOUNCE_COUNT_21", "BOUNCE_COUNT_55", "BOUNCE_COUNT_200"),
    "crosses": ("CROSS_9_21_occurred", "CROSS_9_21_direction", "CROSS_9_21_magnitude",
                "CROSS_21_55_occurred", "CROSS_21_55_direction", "CROSS_21_55_magnitude",
                "CROSS_55_200_occurred", "CROSS_55_200_direction", "CROSS_55_200_magnitude"),
    "scores": ("COHERENCE_SCORE", "FRICTION_INDEX"),
}
VARIABLES = tuple(v for g in GROUPS.values() for v in g)
CROSS_PAIRS = ((9, 21), (21, 55), (55, 200))


class EMAParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    frm: FRMParams = FRMParams()
    min_bars: int = 30
    warmup_bars: int = 200  # EMA-200 estable
    weights: tuple[float, float, float] = (0.4, 0.3, 0.3)  # stack, precio vs stack, pendientes
    cross_lookback: int = 24  # cruces recientes que se reportan/marcan
    horizon_bars: int = 12
