"""Parámetros del agente `smart_money` (T41). La evaluación de líderes: `eim/copytrading/`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SmartMoneyParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Un líder no domina: su peso normalizado se limita a esta fracción. Con un solo líder
    # aprobado el sesgo queda en ±max_leader_share como mucho.
    max_leader_share: float = Field(default=0.4, gt=0, le=1)
    # Postura de un líder = tanh(exposición / escala), exposición = nocional neto en la
    # moneda / valor de su cuenta (si se desconoce, / nocional total de sus posiciones).
    exposure_scale: float = Field(default=1.0, gt=0)
    full_leaders: int = Field(default=3, ge=1)  # líderes aprobados para cobertura plena
    fresh_ms: int = Field(default=5 * 60_000, ge=0)  # foto de posiciones plenamente vigente
    stale_ms: int = Field(default=10 * 60_000, gt=0)  # más vieja: el líder no vota
    horizon_min_bars: int = Field(default=1, ge=1)
    horizon_max_bars: int = Field(default=48, ge=1)
    default_hold_ms: int = Field(default=4 * 3_600_000, gt=0)  # si no hay duración medida
    quote_suffixes: tuple[str, ...] = ("USDT", "USDC", "USD")
