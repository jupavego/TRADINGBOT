"""Pre-registro de T137 (versiones de entrada): inmutable y con huella, como los de T49 y T131.

Cambiar una estrategia, una geometría, un tope, una ventana o una lectura es un archivo NUEVO en
`prereg/` (`prereg_t137_v2.json`), nunca una edición de uno publicado: el SHA-256 de cada versión
queda fijado aquí y, si alguien edita el archivo, la carga falla con el motivo. Así nada de lo que
decide el resultado puede ajustarse después de haberlo visto.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eim.validation.criteria import PUBLISHED as CRITERIA_PUBLISHED
from eim.validation.criteria import file_hash

PREREG_DIR = Path(__file__).parent / "prereg"
DEFAULT_VERSION = "prereg_t137_v1"
# SHA-256 (fin de línea LF) de cada versión publicada. Solo se añaden entradas.
PUBLISHED: dict[str, str] = {
    "prereg_t137_v1": "a5713685b9a67c0d3f15474b488c3cbc736fc2aba3dc10d56fb4ecaaf867dbb5",
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class DataSpec(_Frozen):
    root: str
    contexts: str
    registry: str
    ideas: str


class Strategies(_Frozen):
    scope: str
    sids: int = Field(ge=1)
    by_timeframe: dict[str, int]
    control: str


class ExitSpec(_Frozen):
    policy: Literal["sombra"]
    detail: str
    tp: str
    be: str
    m0_only_in_regression: str


class M8Spec(_Frozen):
    policy: Literal["M8"]
    q: float = Field(gt=0, lt=1)
    reference: str
    min_trades: int = Field(ge=1)
    mae_sigma: str
    floor_sigma: str
    unit_note: str
    without_sample: str


class S1Spec(_Frozen):
    policy: Literal["S1"]
    d_min_sigma: float = Field(gt=0)
    sigma: str


class Geometry(_Frozen):
    m8: M8Spec
    s1: S1Spec
    common: str


class CostCap(_Frozen):
    max_cost_r: float = Field(gt=0)
    est_cost_frac: float = Field(gt=0)
    formula: str
    sl: str
    when: str


class VariantSpec(_Frozen):
    id: str
    n: int = Field(ge=1000)                  # muy por encima de los `n` de las versiones vivas
    geometry: Literal["m8", "s1"] | None
    cost_cap: bool


class Attempts(_Frozen):
    per_variant: int = Field(ge=1)
    total: int = Field(ge=1)
    prior_keys: int = Field(ge=0)
    family: int = Field(ge=1)
    null_reps: int = Field(ge=1)
    rule: str


class Span(_Frozen):
    from_: str = Field(alias="from")
    to: str
    note: str


class Windows(_Frozen):
    selection: Span
    m8_fit_15m: Span
    parent: str


class BankFolds(_Frozen):
    from_: str = Field(alias="from")
    to: str
    fit_months: int = Field(ge=1)
    test_months: int = Field(ge=1)
    step_months: int = Field(ge=1)
    note: str


class FrozenFold(_Frozen):
    fit_from: str
    fit_to: str
    test_from: str
    timeframes: tuple[str, ...]
    note: str


class M8Folds(_Frozen):
    embargo_hours: float = Field(ge=0)
    bank: BankFolds
    after_bank: FrozenFold
    tf15m: FrozenFold


class Reading(_Frozen):
    id: Literal["oficial", "reserva", "banco"]
    verdict: bool
    note: str
    rule: str = ""
    ranges: tuple[tuple[str, str | None], ...] = ()
    timeframes: tuple[str, ...] = ()


class LiveRule(_Frozen):
    alta: str
    rule: str
    consequence: str


class ControlSpec(_Frozen):
    strategy: str
    timeframe: str
    quantile_source: str
    real_from: str
    null: str
    surrogates: int = Field(ge=1)
    bars: int = Field(ge=1)
    ideas: int = Field(ge=1)
    block_minutes: int = Field(ge=1)
    alpha: float = Field(gt=0, lt=0.5)
    ideas_geometry: str
    min_moved_frac: float = Field(gt=0, le=1)
    expect: str


class Timeframe15m(_Frozen):
    measured: bool
    note: str


class Regression(_Frozen):
    rule: str
    tolerance_r: float = Field(gt=0)


class DecisionRule(_Frozen):
    verdict: str
    candidate: str
    not_changed: str


class Prereg(_Frozen):
    version: str
    sha256: str = ""
    declared: str
    description: str
    mode: Literal["SIMULADO"]
    symbol: str
    symbol_why: str
    seed: int
    criteria: str
    criteria_sha256: str
    data: DataSpec
    strategies: Strategies
    exit: ExitSpec
    geometry: Geometry
    cost_cap: CostCap
    variants: tuple[VariantSpec, ...]
    attempts: Attempts
    windows: Windows
    m8_folds: M8Folds
    readings: tuple[Reading, ...]
    live_rule: LiveRule
    control: ControlSpec
    timeframe_15m: Timeframe15m
    regression: Regression
    decision_rule: DecisionRule
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> Prereg:
        """Las cuentas que el pre-registro declara tienen que cuadrar entre sí."""
        a = self.attempts
        if a.total != a.per_variant * len(self.variants):
            raise ValueError(f"intentos: {a.total} ≠ {a.per_variant} × {len(self.variants)}")
        if a.family != a.prior_keys + a.total:
            raise ValueError(f"familia de Holm: {a.family} ≠ {a.prior_keys} + {a.total}")
        if a.per_variant != self.strategies.sids or sum(
                self.strategies.by_timeframe.values()) != self.strategies.sids:
            raise ValueError("los intentos por variante no cuadran con las estrategia@marco")
        if len({v.n for v in self.variants}) != len(self.variants):
            raise ValueError("variantes con el mismo número de versión")
        if [r.id for r in self.readings if r.verdict] != ["oficial"]:
            raise ValueError("solo la lectura oficial puede dar veredicto")
        return self

    def variant(self, vid: str) -> VariantSpec:
        for v in self.variants:
            if v.id == vid:
                return v
        raise KeyError(f"{vid} no es una variante de {self.version}")

    def reading(self, rid: str) -> Reading:
        for r in self.readings:
            if r.id == rid:
                return r
        raise KeyError(f"{rid} no es una lectura de {self.version}")


def load_prereg(version: str = DEFAULT_VERSION, path: str | Path | None = None,
                strict: bool = True) -> Prereg:
    """Lee y valida una versión; si está publicada, su hash y el de sus criterios deben coincidir.

    `strict=False` solo lo usan las pruebas que construyen un pre-registro de juguete: en producción
    un archivo publicado y modificado tiene que fallar.
    """
    p = Path(path) if path is not None else PREREG_DIR / f"{version}.json"
    raw = p.read_bytes()
    data = json.loads(raw)
    if data.get("version") != p.stem:
        raise ValueError(f"versión '{data.get('version')}' no coincide con el archivo {p.name}")
    digest = file_hash(raw)
    pinned = PUBLISHED.get(p.stem)
    if strict and pinned is not None and pinned != digest:
        raise ValueError(f"{p.name} fue modificado después de publicarse: cualquier cambio es una "
                         f"versión nueva (prereg_t137_vN+1), no una edición. Huella: {digest}")
    out = Prereg(**data, sha256=digest)
    if strict and CRITERIA_PUBLISHED.get(out.criteria) != out.criteria_sha256:
        raise ValueError(f"{p.name} apunta a otros criterios que los publicados ({out.criteria})")
    return out
