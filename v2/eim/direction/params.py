"""Reglas pre-registradas de la boleta de dirección (T190–T193), `direccion_v1`.

Congeladas el 2026-11-18 antes de calcular ningún acierto por informante en vivo
(`PLAN/notas/T190_preregistro.md`). Cambiar un número es una versión nueva, no un ajuste.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

PREREG_ID = "direccion_v1"
SYNTH_ID = "sintesis_v1"
REGIMES: tuple[str, ...] = ("baja", "media", "alta")


class DirectionParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    prereg: str = PREREG_ID
    frozen_on: str = "2026-11-18"
    # --- boleta (T190) ---------------------------------------------------------------
    horizons: tuple[int, ...] = (1, 4, 12)      # velas del marco
    primary: int = 4                            # horizonte que decide veredictos y sombras
    bias_min: float = 0.05                      # |sesgo| mínimo para contar como voto
    # sin opinión de dirección por su papel (riesgo, carril, derivado)
    excluded: frozenset[str] = frozenset({"calendar", "arbitrage", "plan", "regime"})
    regime_bars: int = 24                       # volatilidad realizada de las últimas N velas
    regime_lookback: int = 500                  # frente a su distribución en las N anteriores
    max_instants: int = 20_000                  # instantes guardados que se leen como máximo
    min_eff_verdict: int = 100                  # votos sin solape para dar veredicto
    edge_min_eff: int = 250                     # … para declarar ventaja o señal contraria
    alpha: float = 0.05                         # Holm, una cola
    # --- vigía (T191) ----------------------------------------------------------------
    interval_ms: int = 6 * 3_600_000
    # --- sombras (T192, T193) --------------------------------------------------------
    qualify_min: int = 100                      # votos resueltos sin solape por (agente, régimen)
    min_agree: int = 2                          # calificados que deben coincidir (T192)
    prior_strength: float = 100.0               # encogimiento hacia el 50 % (T193)
    gate_min_pairs: int = 250
    gate_min_delta: float = 0.03
    gate_streak: int = 2                        # revisiones seguidas para «sostenida»
    first_reading: str = "2026-11-28"
    readings: tuple[str, ...] = ("2026-11-28", "2026-12-26", "2027-01-23")
    close_line: str = "2027-02-20"
