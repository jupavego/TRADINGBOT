"""Parámetros del agente `intermarket` (T183)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IntermarketParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    equities: tuple[str, ...] = ("NASDAQ", "SP500")  # apetito por riesgo (EE. UU.)
    haven: str = "XAUUSDT"           # refugio
    mom_days: int = 20               # sesiones del impulso (≈ un mes bursátil)
    vol_days: int = 60               # sesiones para la volatilidad diaria que normaliza el impulso
    sma_days: int = 50               # tendencia: cierre sobre o bajo su media de 50 sesiones
    corr_days: int = 60              # sesiones comunes para la correlación cripto–índice
    min_common: int = 30             # mínimo de sesiones comunes para opinar
    z_scale: float = 2.0             # puntuación = tanh(z / z_scale): z ±2 ≈ ±0,76
    regime_band: float = 0.25        # |puntuación| desde la que se habla de risk-on / risk-off
    stale_days: int = 5              # vela diaria más reciente más vieja que esto → sin datos
    max_confidence: float = 0.5      # contexto, no señal: nunca más que un agente moderado
    horizon_days: int = 5            # lo que dura una lectura de contexto diaria
