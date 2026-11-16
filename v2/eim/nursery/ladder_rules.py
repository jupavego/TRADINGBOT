"""Umbrales del escalafón de la cantera (T170): forma validada e inmutable de `cantera_v1`.

Los valores viven en `eim/validation/prereg/prereg_cantera_v1.json` (con su huella fijada en
`nursery/prereg.py`); aquí solo está su forma. Cambiar un valor es `cantera_v2`, con reloj nuevo.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NurseryExit(_Frozen):
    min_trades: int = Field(ge=1)          # guardería → cantera con n ≥ 30 …
    max_days: int = Field(ge=1)            # … o a los 60 días si es lento


class ClearlyNegative(_Frozen):
    z: float = Field(ge=0)                 # media de d̃ + z·EE < 0
    min_trades: int = Field(ge=2)


class Primary(_Frozen):
    clip_r: float = Field(gt=0)            # B: d̃ = recorte(d, ±B)
    lambdas: tuple[float, ...]             # rejilla de apuestas del e-proceso mezcla
    day_unit_bands: tuple[str, ...]        # bandas medidas por día (suma diaria de d)


class Promise(_Frozen):
    q: float = Field(gt=0, lt=1)           # e-BH
    max_trade_share: float = Field(gt=0, le=1)   # consistencia
    sibling_alpha: float = Field(gt=0, lt=0.5)   # hermano simple: a empate, el simple
    sibling_min_trades: int = Field(ge=2)
    marginal_corr: float = Field(gt=0, lt=1)     # contribución marginal
    marginal_min_days: int = Field(ge=2)


class Futility(_Frozen):
    mu_min_r: float = Field(gt=0)
    beta: float = Field(gt=0, lt=0.5)
    min_trades: int = Field(ge=2)


class Drawdown(_Frozen):
    target_edge_r: float = Field(gt=0)
    sigma_r: float = Field(gt=0)
    p_unfair: float = Field(gt=0, lt=0.5)
    risk_pct: float = Field(gt=0, le=0.02)
    n_without_history: int = Field(ge=1)
    sims: int = Field(ge=1000)
    seed: int
    caps_pct: dict[str, float]             # tope calibrado por prospecto (% del saldo máximo)


class Inactivity(_Frozen):
    days: int = Field(ge=1)                # sin operaciones en 60 días → baja …
    gate_closed_counts: bool               # … sin contar los días con el marco cerrado


class ForwardExam(_Frozen):
    """Examen físico hacia adelante de los prospectos sin historia: la ficha de T169 tal cual."""
    min_ops_month: dict[str, float]
    min_pos_days_frac: float = Field(gt=0, le=1)
    max_cost_r: float = Field(gt=0)
    min_closed_for_band: int = Field(ge=1)
    band_max_hours: tuple[float, float, float]     # scalping ≤, intradía <, tres días ≤


class FirstTeam(_Frozen):
    stepm_size: float = Field(gt=0, lt=0.5)
    stepm_reps: int = Field(ge=1000)
    stepm_seed: int
    dsr_min: float = Field(gt=0, lt=1)
    neff_corr: float = Field(gt=0, lt=1)
    regimes_min: int = Field(ge=1)
    regime_min_trades: int = Field(ge=1)
    persistence_min_trades: int = Field(ge=1)
    min_trades: int = Field(ge=1)          # V1 (bandas por operación)
    min_pos_days: int = Field(ge=1)        # V1 (banda semanal)
    max_dd: float = Field(gt=0, lt=1)      # V4
    window_days: int = Field(ge=1)         # V5
    window_min_trades: int = Field(ge=1)
    min_windows: int = Field(ge=1)
    min_positive_frac: float = Field(gt=0, le=1)
    max_cost_r: float = Field(gt=0)        # V6


class LadderRules(_Frozen):
    reviews_days: tuple[int, ...]
    nursery_exit: NurseryExit
    clearly_negative: ClearlyNegative
    primary: Primary
    promise: Promise
    futility: Futility
    drawdown: Drawdown
    inactivity: Inactivity
    forward_exam: ForwardExam
    first_team: FirstTeam

    @model_validator(mode="after")
    def _coherent(self) -> LadderRules:
        r = self.reviews_days
        if not r or list(r) != sorted(set(r)) or r[0] <= 0:
            raise ValueError("las revisiones deben ser días crecientes y positivos")
        if any(not 0 < x < 1 for x in self.primary.lambdas) or not self.primary.lambdas:
            raise ValueError("la rejilla de apuestas debe estar en (0, 1)")
        if self.nursery_exit.max_days > r[-1]:
            raise ValueError("la guardería no puede durar más que la fase")
        return self

    @property
    def deadline_days(self) -> int:
        return self.reviews_days[-1]

    @property
    def looks(self) -> int:
        return len(self.reviews_days)
