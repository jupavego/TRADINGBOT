"""Parámetros del agente `microstructure`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MicrostructureParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    window: int = 6  # velas recientes que forman la señal (OFI, delta, divergencia)
    min_bars: int = 24  # velas con datos de recolección mínimas (historia para el z-score)
    min_window_bars: int = 3  # velas de la ventana con datos para emitir señal
    vol_window: int = 48  # velas para volatilidad realizada
    vol_long_window: int = 200  # referencia para detectar expansión de volatilidad
    vol_expansion: float = 1.5  # razón corta/larga que se advierte
    max_incomplete: float = 0.3  # fracción de velas con huecos que degrada el reporte
    w_ofi: float = 0.4
    w_delta: float = 0.3
    w_depth: float = 0.15
    w_divergence: float = 0.15
    z_scale: float = 2.0  # tanh(z / z_scale): z=2 ≈ 76 % del peso
    price_move: float = 0.0005  # |retorno| mínimo para evaluar divergencia precio/CVD
    max_confidence: float = 0.6  # señal de corto plazo: nunca alta confianza
    horizon_bars: int = 3
