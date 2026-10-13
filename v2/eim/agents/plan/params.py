"""Parámetros del agente `plan` (sin números mágicos en la lógica)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PlanParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_bars: int = 120
    atr_period: int = 14
    # Dirección y confianza
    min_abs_bias: float = 0.15       # sesgo combinado mínimo para proponer dirección
    min_confidence: float = 0.30     # confianza mínima para emitir plan
    disagree_penalty: float = 0.5    # factor de confianza si structure y levels discrepan
    # Niveles
    sl_buffer_atr: float = 0.5       # colchón más allá del nivel de invalidación
    min_sl_atr: float = 0.5          # el nivel de invalidación debe estar al menos a esta distancia
    max_sl_atr: float = 5.0          # SL más lejos que esto → sin plan
    tp_min_gap_atr: float = 0.5      # separación mínima entre TP1 y TP2
    min_rr: float = 1.5              # R:R mínimo (a TP1)
    # Ciclo de vida
    expiry_bars: int = 48
    cooldown_bars: int = 4           # velas sin proponer tras cerrar un plan
    improve_atr: float = 1.0         # mejora mínima del SL para justificar revisión
    replay_bars: int = 96            # ventana reproducida para reconstruir el estado
    replay_step: int = 6             # cada cuántas velas se reevalúa una propuesta
    show_resolved_bars: int = 3      # cuánto se muestra un plan recién resuelto
    horizon_bars: int = 24
    max_confidence: float = 0.85
