"""Parámetros del agente `calendar` (riesgo de evento; no direccional)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CalendarParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Fuentes macro que deben estar presentes y frescas para un calendario completo.
    expected_sources: tuple[str, ...] = ("fed_fomc", "bls", "bea")
    stale_hours: float = 48.0      # consulta más antigua que esto → fuente obsoleta
    horizon_days: float = 7.0      # cada fuente debe conocer eventos hasta asof + 7 d
    # Ventana de riesgo alrededor de cada evento (minutos antes / después) por impacto.
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
