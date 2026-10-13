"""Parámetros del agente `vwap`. Heurísticas heredadas de F7/eim_vwap.py (no calibradas)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

PERIODS = ("daily", "weekly", "quincenal", "monthly")
# Prefijo de columna por período (mismos nombres que el legado).
PREFIX = {"daily": "VWAP_DAY", "weekly": "VWAP_WEEK",
          "quincenal": "VWAP_QUINCENA", "monthly": "VWAP_MONTH"}
LABEL = {"daily": "diario", "weekly": "semanal", "quincenal": "quincenal", "monthly": "mensual"}

# Sesgo heurístico por posición (puntos sobre base neutra 50).
POSITION_BIAS = {
    "SOBRE_VWAP": 15, "ESTIRADO_SOBRE": 6, "EXTREMO_SOBRE": -8,
    "BAJO_VWAP": -15, "ESTIRADO_BAJO": -6, "EXTREMO_BAJO": 8, "SIN_DATOS": 0,
}

POSITION_NOTES = {
    "SOBRE_VWAP": "Cotiza ligeramente por encima del precio promedio ponderado — "
                  "sesgo comprador de corto plazo, dentro de rango normal.",
    "ESTIRADO_SOBRE": "Se aleja del VWAP (1-2σ) — puede continuar, pero crece la "
                      "probabilidad de un retroceso hacia el VWAP.",
    "EXTREMO_SOBRE": "Muy alejado del VWAP (>2σ) — estadísticamente sobreextendido; "
                     "tiende a revertir hacia el VWAP.",
    "BAJO_VWAP": "Cotiza ligeramente por debajo del precio promedio ponderado — "
                 "sesgo vendedor de corto plazo, dentro de rango normal.",
    "ESTIRADO_BAJO": "Se aleja del VWAP hacia abajo (1-2σ) — puede continuar, pero crece "
                     "la probabilidad de un rebote hacia el VWAP.",
    "EXTREMO_BAJO": "Muy alejado del VWAP hacia abajo (>2σ) — estadísticamente sobrevendido; "
                    "tiende a revertir hacia el VWAP.",
    "SIN_DATOS": "Inicio de período — aún no hay volumen acumulado suficiente.",
}


class VWAPParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_bars: int = 24
    slope_gain: float = 40.0  # puntos de sesgo por 1 % de pendiente
    slope_cap: float = 20.0
    prob_floor: float = 5.0
    prob_cap: float = 95.0
    # Peso de cada período en el sesgo agregado.
    period_weights: dict[str, float] = {"daily": 1.0, "weekly": 1.0, "quincenal": 1.0,
                                        "monthly": 1.0}
    overlay_bands: tuple[int, ...] = (1, 2)  # ±1σ y ±2σ además del VWAP
    horizon_bars: int = 24
    max_confidence: float = 0.6  # heurística no validada: nunca se declara certeza alta
