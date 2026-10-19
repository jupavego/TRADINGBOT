"""Proyección probabilística (siempre 3 escenarios) y síntesis."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from eim.core.market import Candle, Frozen

ScenarioId = Literal["bull", "neutral", "bear"]


class Scenario(Frozen):
    """Escenario proyectado. Las velas son SIMULADAS, no datos reales."""

    id: ScenarioId
    probability: float = Field(ge=0, le=1)
    path: list[tuple[int, float]]  # mediana (t, p)
    band_low: list[tuple[int, float]]
    band_high: list[tuple[int, float]]
    candles: list[Candle]  # secuencia OHLC representativa, simulada
    invalidation: dict  # {level, condition}
    narrative: str
    n_paths: int = Field(ge=1)
    engine: str
    # Techo y piso del escenario (T19+): [{role, price, source, methods, confluence, note}].
    levels: list[dict] = []


class ForecastSet(Frozen):
    """Exactamente 3 escenarios (bull/neutral/bear) cuya probabilidad suma 1."""

    symbol: str
    timeframe: str
    made_at: int
    horizon_bars: int = Field(ge=20, le=30)
    scenarios: list[Scenario]
    engine: str
    baseline_engine: str
    warnings: list[str] = []
    # Cuantiles del cierre simulado por instante sobre TODAS las trayectorias ('5'..'95'); T19.
    quantiles: dict[str, list[tuple[int, float]]] = {}
    # Ajustes aplicados a las probabilidades tras el motor (T54): [{id, k, label, net,
    # base_probability}]. Vacío = las probabilidades son las del motor.
    adjustments: list[dict] = []

    @model_validator(mode="after")
    def _check_scenarios(self) -> ForecastSet:
        if sorted(s.id for s in self.scenarios) != ["bear", "bull", "neutral"]:
            raise ValueError("se requieren exactamente 3 escenarios: bull, neutral, bear")
        if abs(sum(s.probability for s in self.scenarios) - 1.0) > 1e-6:
            raise ValueError("las probabilidades de los 3 escenarios deben sumar 1")
        return self


class Synthesis(Frozen):
    """Consenso de los agentes."""

    bias: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    agreement: float = Field(ge=0, le=1)
    contributions: dict[str, float]
    thesis: str
    # T44 (aditivos): peso base efectivo de cada agente que vota (peso × régimen × correlación;
    # 0 = a la vista pero sin voto) y factores aplicados a la confianza ("desacuerdo", "evento").
    weights: dict[str, float] = {}
    factors: dict[str, float] = {}
