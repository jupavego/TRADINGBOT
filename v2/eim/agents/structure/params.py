"""Parámetros del agente `structure` (FRM → BRM → IRM). Todo umbral/peso vive aquí.

Valores provisionales heredados de EIM-BRM-001 / EIM-IRM-001 (calibración en VRM Fase VI).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# Escenarios y estados (códigos canónicos de los documentos F4/F5)
SCENARIOS = (
    "SC-01_CONTINUATION",
    "SC-02_BREAKOUT",
    "SC-03_PULLBACK",
    "SC-04_STRUCTURAL_CHANGE",
    "SC-05_CONSOLIDATION",
)


class FRMParams(BaseModel):
    """Ventanas y pesos de las fórmulas F-001…F-022."""

    model_config = ConfigDict(frozen=True)

    volume_window: int = 20
    bounce_window: int = 50
    atr_period: int = 14
    theta_compress: float = 0.5  # θ-001 usado en COMPRESSION_DURATION
    # F-011 coherencia: stack, precio, sync, volumen, rebotes
    coherence_weights: tuple[float, float, float, float, float] = (0.30, 0.30, 0.20, 0.10, 0.10)
    # F-012 fricción: compresión, elasticidad, volumen, duración, ATR
    friction_weights: tuple[float, float, float, float, float] = (0.35, 0.25, 0.20, 0.10, 0.10)


class BRMParams(BaseModel):
    """Umbrales θ-001…θ-007 (EIM-BRM-001)."""

    model_config = ConfigDict(frozen=True)

    theta_001_compress: float = 0.50
    theta_002_expand: float = 2.00
    theta_003_elastic: float = 5.00
    theta_004_velocity: float = 0.05
    theta_005_curvature: float = 0.02
    theta_006_duration: int = 5
    theta_007_persistence: int = 3
    atr_high: float = 0.5  # R-003 alta energía
    atr_low: float = 0.3  # R-003 baja energía


class IRMParams(BaseModel):
    """Tablas CS-001…CS-004, reglas SR-001…SR-004 y modificadores M-001…M-007."""

    model_config = ConfigDict(frozen=True)

    # CS-001: (score alcista, score bajista) por estado estructural
    base_scores: dict[str, tuple[float, float]] = {
        "E-01_TREND_STRONG": (95, 5),
        "E-03_ORDERED": (75, 25),
        "E-02_TREND_WEAK": (62, 38),
        "E-06_EXPANDING": (70, 30),
        "E-04_EXHAUSTED": (50, 50),
        "E-05_COMPRESSED": (50, 50),
        "E-07_DIVERGENT": (50, 50),
    }
    momentum_mult: dict[str, float] = {
        "ACCELERATING": 1.20,
        "STABLE": 1.00,
        "DECELERATING": 0.80,
        "REVERSING": 0.60,
    }
    energy_delta: dict[str, float] = {
        "HIGH_ENERGY": 8,
        "MODERATE_ENERGY": 0,
        "LOW_ENERGY": -5,
        "COMPRESSED": 3,
    }
    # CS-004: (fricción mínima, delta) evaluado de mayor a menor; último = por defecto
    friction_bands: tuple[tuple[float, float], ...] = ((8.0, -8), (5.0, -3), (2.0, 0))
    friction_default: float = 4
    # SR-001…SR-003
    sr1_friction: float = 7.0
    sr2_conviction_band: tuple[float, float] = (40, 60)
    sr2_coherence: float = 5.0
    sr3_mtf_min: float = 50.0
    # Confianza
    confidence_cap: float = 95.0
    horizon_bars: int = 12  # horizonte declarado del agente (velas)


class StructureParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    frm: FRMParams = FRMParams()
    brm: BRMParams = BRMParams()
    irm: IRMParams = IRMParams()
    min_bars: int = 60  # por debajo, no_data
    warmup_bars: int = 400  # recomendado para EMA-200 (FRM § validación)
