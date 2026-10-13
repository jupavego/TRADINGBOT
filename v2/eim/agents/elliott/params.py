"""Parámetros del agente `elliott` (heurística, no conteo objetivo)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

LABELS = ("0", "1", "2", "3", "4", "5", "A", "B", "C")
NEXT_LABEL = {"0": "1", "1": "2", "2": "3", "3": "4", "4": "5",
              "5": "A", "A": "B", "B": "C", "C": None}

# Confianza (%) de que el tramo en formación (último pivote, sin confirmar) siga extendiéndose
# antes de revertir. Base 50 = sin lectura clara. Heurística explícita, no estadística validada.
CONTINUATION_CONFIDENCE = {"0": 50, "1": 55, "2": 40, "3": 65, "4": 40, "5": 35,
                           "A": 55, "B": 40, "C": 50}

WAVE_NOTES = {
    "0": "Punto de partida del conteo — sin lectura direccional todavía.",
    "1": "Onda 1 (impulso inicial) — puede extenderse o revertir pronto; lectura poco definida.",
    "2": "Onda 2 (corrección) — típicamente acotada por Fibonacci; probable que revierta pronto "
         "retomando la tendencia.",
    "3": "Onda 3 (impulso, suele ser la más extensa) — mayor probabilidad de que el movimiento "
         "actual continúe.",
    "4": "Onda 4 (corrección) — típicamente acotada; probable que revierta pronto retomando la "
         "tendencia.",
    "5": "Onda 5 (impulso final, suele mostrar agotamiento/divergencia) — mayor probabilidad de "
         "reversión próxima.",
    "A": "Onda A (inicio de corrección) — puede extenderse o revertir; lectura poco definida.",
    "B": "Onda B (rebote dentro de la corrección) — típicamente acotada; probable reversión "
         "retomando la corrección.",
    "C": "Onda C (cierre de la corrección) — punto de mayor incertidumbre; posible inicio de un "
         "nuevo ciclo.",
}


class ElliottParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    threshold_pct: float = 3.0  # reversión mínima (%) para confirmar un pivote zigzag
    min_bars: int = 30
    horizon_bars: int = 12
    base_confidence: float = 0.35  # conteo completo y sin violaciones; baja si hay violaciones
