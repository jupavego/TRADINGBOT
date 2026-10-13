"""Parámetros del agente `price_action` (valores del legado F7/eim_price_action.py)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PriceActionParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    fractal_n: int = 2  # velas a cada lado para confirmar un swing
    sr_tolerance_pct: float = 0.5  # clustering de pivotes
    min_bars: int = 20
    pattern_lookback: int = 5  # velas recientes que votan por patrones
    event_lookback: int = 24  # antigüedad máxima de un BOS/CHOCH que aporta confianza
    structure_weight: float = 0.6  # peso de la estructura en el sesgo (resto: patrones)
    max_zones: int = 8  # zonas S/R más cercanas al precio que se dibujan
    zone_min_touches: int = 2
    horizon_bars: int = 12
    max_confidence: float = 0.7
