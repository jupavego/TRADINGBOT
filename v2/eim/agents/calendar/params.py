"""Parámetros del agente `calendar` (riesgo de evento; no direccional)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EventWindow(BaseModel):
    """Ventana de pausa de una publicación fijada por evidencia (T37)."""
    model_config = ConfigDict(frozen=True)

    pre: int                 # minutos antes de la publicación
    post: int                # minutos después; pre = post = 0 → sin ventana de riesgo
    blackout: bool           # si abre `blackout` (veto en T29)
    evidence: str            # cita: n por activo, cociente de rango y p con Holm


# Estudio de eventos T37 (`python -m eim.analytics.event_report`, reports/calendar_impact.md):
# velas 15 m BTC/ETH; "normal" = misma hora UTC en 20 días hábiles previos sin eventos; p =
# bootstrap con Holm; ventana = velas contiguas a t0 con rango ≥ ×1.25 significativo (+ la
# ventana −60…0 si es significativa); máximo entre activos. Cociente = rango de la vela t0.
# Con pre = 0 el veto empieza igualmente una vela antes (`lookahead_bars`).
T37_WINDOWS: dict[str, EventWindow] = {
    "Decisión de tipos FOMC": EventWindow(pre=30, post=225, blackout=True, evidence=(
        "n=30/30 (2023-02…2026-09); vela t0 ×2.97/×3.50, p Holm 0.005; velas −30…+225 "
        "significativas en ETH; en BTC −15…+165 y +195…+210")),
    "Consumer Price Index": EventWindow(pre=15, post=30, blackout=True, evidence=(
        "n=21/21 (2025-01…2026-10); t0 ×3.39/×3.68, p Holm 0.005; −15 ×1.40/×1.51 y +15 "
        "significativas")),
    "Employment Situation": EventWindow(pre=0, post=45, blackout=True, evidence=(
        "n=21/21; t0 ×3.21/×3.40, p Holm 0.005; +15 y +30 significativas")),
    "Producer Price Index": EventWindow(pre=0, post=30, blackout=True, evidence=(
        "n=20/20; t0 ×2.12/×2.19, p Holm 0.005; +15 significativa en BTC")),
    "Gross Domestic Product": EventWindow(pre=0, post=15, blackout=True, evidence=(
        "n=20/20; t0 ×1.70/×1.79, p Holm 0.015/0.005; 10 de 20 a la vez que PCE")),
    "Personal Income and Outlays": EventWindow(pre=0, post=15, blackout=True, evidence=(
        "n=20/20; t0 ×1.75/×1.76, p Holm 0.010/0.005; 11 de 20 a la vez que el PIB")),
    "Job Openings and Labor Turnover Survey": EventWindow(pre=0, post=15, blackout=True,
        evidence="n=21/21; t0 ×1.37/×1.44, p Holm 0.020/0.010"),
    "Vencimiento futuros trimestrales Binance (BTC/ETH)": EventWindow(
        pre=60, post=0, blackout=True, evidence=(
            "n=13/13 (2023-03…2026-09); ventana −60…0 ×1.37 en BTC, p Holm 0.020 (ETH ×1.33, "
            "no significativa); sin efecto después de las 08:00")),
    "U.S. International Trade in Goods and Services": EventWindow(
        pre=0, post=0, blackout=False, evidence=(
            "n=22/22; t0 ×1.11/×1.15, p Holm 1.0: no mueve el mercado → sin ventana")),
    # Employment Cost Index: n=7 < 12 → sin evidencia suficiente; usa la ventana por impacto.
}


class CalendarParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Fuentes macro que deben estar presentes y frescas para un calendario completo.
    expected_sources: tuple[str, ...] = ("fed_fomc", "bls", "bea")
    stale_hours: float = 48.0      # consulta más antigua que esto → fuente obsoleta
    horizon_days: float = 7.0      # cada fuente debe conocer eventos hasta asof + 7 d
    # Ventanas por publicación con evidencia (T37); tienen prioridad sobre las de impacto.
    event_windows: dict[str, EventWindow] = T37_WINDOWS
    # Ventana por impacto para publicaciones SIN evidencia (minutos antes / después).
    pre_minutes: dict[str, int] = {"alto": 60, "medio": 15}
    post_minutes: dict[str, int] = {"alto": 60, "medio": 15}
    # Post-evento más largo por fuente (prefijo del id): rueda de prensa FOMC a las 14:30 ET.
    post_minutes_by_source: dict[str, int] = {"fed_fomc": 120}
    blackout_impacts: tuple[str, ...] = ("alto",)  # solo estos abren `blackout` (veto en T29)
    # `blackout` también si la ventana empieza dentro de las próximas N velas (el reporte se
    # usa hasta la siguiente vela; el motor de riesgo no reevalúa la hora del evento).
    lookahead_bars: int = 1
    upcoming_max: int = 8
    # σ histórica de (real − previsto) por publicación para estandarizar la sorpresa (T37).
    surprise_sd: dict[str, float] = {}
    horizon_bars: int = 0
