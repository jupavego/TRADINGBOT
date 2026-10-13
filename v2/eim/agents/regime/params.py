"""Parámetros del agente `regime`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RegimeParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_bars: int = 120  # velas mínimas para correr BOCPD y las métricas de estabilidad
    hazard: float = 1 / 800  # probabilidad a priori de cambio por vela
    max_run: int = 300  # truncado de la longitud de racha (acota coste y memoria)
    short_run: int = 5  # masa de P(racha <= short_run) = "cambio reciente"
    min_gap: int = 12  # separación mínima entre puntos de cambio (dedupe retornos/volatilidad)
    min_drop: int = 8  # una racha MAP debe caer al menos esto para contar como cambio
    recent_bars: int = 10  # ventana para "probabilidad de cambio reciente"
    # Etiquetado (sobre el tramo actual del BOCPD, con ventana mínima `min_seg`)
    min_seg: int = 24
    trend_t: float = 2.0  # |t-stat| de la media del tramo para llamarlo tendencia
    vol_ratio: float = 1.6  # sigma del tramo / sigma mediana de los tramos -> volátil
    # Estabilidad del esquema
    min_dwell: float = 10.0  # permanencia media mínima (velas) antes de avisar
    max_entropy: float = 0.85  # entropía normalizada máxima de la matriz de transición
    max_confidence: float = 0.8
    horizon_bars: int = 24
