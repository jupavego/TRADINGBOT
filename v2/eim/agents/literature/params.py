"""Parámetros del agente `literature`: umbrales tomados de las fichas (T52) y metadatos de cita.

Los umbrales vienen de la ficha que cada regla codifica; el agente es puro y no lee archivos, así
que la cita corta de cada ficha se copia aquí (`tests/agents/literature` la compara con la ficha).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CardMeta(BaseModel):
    """Cita corta y mercado original de una ficha codificada (se resuelve completa vía la API)."""

    model_config = ConfigDict(frozen=True)

    author: str
    cite: str                 # «Nison (2001), cap. 4, pp. 45–46»
    markets: tuple[str, ...]  # `applicability.original_market` de la ficha


_NISON = "Nison (2001)"
_MURPHY = "Murphy (1999)"
_MK = ("acciones", "futuros", "divisas")

CARD_META: dict[str, CardMeta] = {
    "nison_hammer": CardMeta(author="Nison", cite=f"{_NISON}, cap. 4, pp. 45–46", markets=_MK),
    "nison_shooting_star": CardMeta(author="Nison", cite=f"{_NISON}, cap. 5, pp. 84–86",
                                    markets=("acciones",)),
    "nison_engulfing": CardMeta(author="Nison", cite=f"{_NISON}, cap. 4, pp. 53–54", markets=_MK),
    "nison_morning_star": CardMeta(author="Nison", cite=f"{_NISON}, cap. 5, pp. 72–73",
                                   markets=("acciones", "índices", "divisas")),
    "nison_evening_star": CardMeta(author="Nison", cite=f"{_NISON}, cap. 5, pp. 76–77",
                                   markets=("acciones", "índices", "divisas")),
    "nison_three_white_soldiers": CardMeta(
        author="Nison", cite=f"{_NISON}, cap. 6, pp. 108–109", markets=("acciones",)),
    "nison_three_black_crows": CardMeta(
        author="Nison", cite=f"{_NISON}, cap. 6, pp. 106–107", markets=("acciones",)),
    "murphy_rsi": CardMeta(author="Murphy", cite=f"{_MURPHY}, cap. 10, pp. 281–283, 285–286",
                           markets=("índices", "futuros")),
    "murphy_weekly_rule": CardMeta(author="Murphy", cite=f"{_MURPHY}, cap. 9, pp. 256–258",
                                   markets=("futuros",)),
}


class LiteratureParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_bars: int = 60             # por debajo: sin datos
    atr_period: int = 14
    horizon_bars: int = 12         # horizonte de la lectura agregada (el autor no da uno)
    overlay_lookback: int = 30     # velas hacia atrás donde se marcan patrones
    # Tendencia previa (Nison: «aunque sea corta»): cambio del cierre en `trend_bars` velas,
    # medido en ATR. Se necesita |cambio| ≥ `trend_atr` para llamarla alcista/bajista.
    trend_bars: int = 5
    trend_atr: float = 1.0
    mature_trend_atr: float = 2.0  # «alza madura» / «movimiento extenso» (refuerzo)
    # Velas
    doji_frac: float = 0.1         # cuerpo ≤ frac·rango = doji / peonza mínima
    long_body_atr: float = 0.8     # «vela larga»: cuerpo ≥ frac·ATR
    small_body_frac: float = 0.5   # estrella: cuerpo ≤ frac·cuerpo de la 1.ª vela
    star_gap_atr: float = 0.1      # tolerancia de solape entre cuerpos (24/7 casi no hay huecos)
    shadow_ratio: float = 2.0      # hammer / shooting star: sombra ≥ ratio·cuerpo (Nison: 2–3)
    shadow_ratio_full: float = 3.0
    body_edge_frac: float = 0.35   # cuerpo dentro del tercio extremo del rango
    far_shadow_frac: float = 0.1   # sombra opuesta ≤ frac·rango
    close_near_extreme: float = 0.25  # soldados/cuervos: cierre a ≤ frac·rango del extremo
    penetration: float = 0.5       # estrellas: 3.ª vela cierra sobre/bajo esta fracción de la 1.ª
    vol_window: int = 20           # refuerzo por volumen: v > vol_ratio × media(vol_window)
    vol_ratio: float = 1.2
    # Murphy: RSI(14), 70/30; Donchian de 4 semanas (calendario, en 24/7)
    rsi_period: int = 14
    rsi_ob: float = 70.0
    rsi_os: float = 30.0
    rsi_lookback: int = 10         # profundidad del extremo previo (refuerzo)
    donchian_days: int = 28
    tf_minutes: dict[str, int] = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    # Agregación y límites (sin medición hasta T54: confianza con techo bajo)
    bias_norm: float = 2.0         # Σ(dir·fuerza)/norma: dos reglas plenas coincidentes = ±1
    max_confidence: float = 0.5
    # Fichas habilitadas (None = todas las codificadas). Vacío → sin reglas → no_data.
    coded_cards: frozenset[str] | None = None
