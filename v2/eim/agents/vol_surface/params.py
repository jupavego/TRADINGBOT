"""Parámetros del agente `vol_surface` (T214). Los de la superficie son los del pre-registro."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from eim.options.surface import SurfaceParams


class VolSurfaceParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_bars: int = 0                    # no necesita velas (la prima de varianza sí, si las hay)
    stale_minutes: int = 120             # toma más vieja: se avisa (el colector toma cada hora)
    max_age_minutes: int = 26 * 60       # más vieja que esto: sin datos
    rv_min_coverage: float = 0.9         # ventana de la realizada cubierta al menos así
    # --- superficie (iguales a `SurfaceParams` y a `PLAN/notas/T214_preregistro.md`) ---------
    tenors_days: tuple[int, int] = (7, 30)
    skew_tenor_days: int = 30
    min_expiry_days: float = 2.0
    min_otm: int = 6
    atm_near: int = 2
    max_mark_gap: float = 0.02
    max_rel_spread: float = 0.25
    delta: float = 0.25

    def surface(self) -> SurfaceParams:
        return SurfaceParams(tenors_days=self.tenors_days, skew_tenor_days=self.skew_tenor_days,
                             min_expiry_days=self.min_expiry_days, min_otm=self.min_otm,
                             atm_near=self.atm_near, max_mark_gap=self.max_mark_gap,
                             max_rel_spread=self.max_rel_spread, delta=self.delta)
