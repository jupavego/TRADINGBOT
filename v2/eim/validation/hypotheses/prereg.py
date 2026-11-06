"""Pre-registro de T139: inmutable y con huella, como los de T49, T131 y T137.

Cambiar una regla, un parámetro, una ventana o la regla de parada es un archivo NUEVO en `prereg/`,
nunca una edición de uno publicado: el SHA-256 queda fijado aquí y, si alguien edita el archivo, la
carga falla con el motivo. Las cuentas de la familia de Holm se comprueban al cargar.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eim.validation.criteria import PUBLISHED as CRITERIA_PUBLISHED
from eim.validation.criteria import file_hash

PREREG_DIR = Path(__file__).parent.parent / "prereg"
DEFAULT_VERSION = "prereg_t139_v1"
# SHA-256 (fin de línea LF) de cada versión publicada. Solo se añaden entradas.
PUBLISHED: dict[str, str] = {
    "prereg_t139_v1": "f24f72bfc3d8cc928b7884f31550e74e9f4e3e5cf04bd27df2dbf29436510d16",
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class ExitSpec(_Frozen):
    sl_atr: float = Field(gt=0)
    tp_atr: float = Field(gt=0)
    conf: float = Field(ge=0, le=1)
    hold_bars: float = Field(gt=0)
    kind: Literal["market"]
    be_timeframes: tuple[str, ...]
    atr: str
    detail: str


class Hypothesis(_Frozen):
    id: str
    strategy: str
    timeframes: tuple[str, ...]
    rule: str
    params: dict[str, float]


class Attempts(_Frozen):
    new: int = Field(ge=1)
    prior_keys: int = Field(ge=0)
    t137_keys: int = Field(ge=0)
    family: int = Field(ge=1)
    null_reps: int = Field(ge=1)
    rule: str


class Span(_Frozen):
    from_: str = Field(alias="from")
    to: str
    note: str


class Windows(_Frozen):
    adjust: Span


class Reading(_Frozen):
    id: Literal["oficial", "banco"]
    verdict: bool
    note: str
    ranges: tuple[tuple[str, str], ...] = ()


class LiveRule(_Frozen):
    alta: str
    deadline: str
    rule: str


class Coverage(_Frozen):
    from_: str = Field(alias="from")
    to: str
    min: float = Field(gt=0, le=1)
    series: tuple[str, ...]
    taker_timeframes: tuple[str, ...]
    rule: str


class Stage(_Frozen):
    id: Literal["cobertura", "banco", "limpia"]
    rule: str


class Regression(_Frozen):
    source: str
    strategy: str
    from_: str = Field(alias="from")
    n: int = Field(ge=1)
    gross_r: float
    tolerance_r: float = Field(gt=0)
    asof: str
    rule: str


class ControlSpec(_Frozen):
    strategy: str
    timeframes: tuple[str, ...]
    null: str
    surrogates: int = Field(ge=1)
    bars: int = Field(ge=1)
    block_minutes: int = Field(ge=1)
    max_ideas: int = Field(ge=1)
    alpha: float = Field(gt=0, lt=0.5)
    null_quantile: float = Field(gt=0, lt=1)
    rule: str


class Baseline(_Frozen):
    families: tuple[str, ...]
    timeframes: tuple[str, ...]
    rule: str


class ReadingRule(_Frozen):
    min_side_trades: int = Field(ge=1)
    cost_stress: float = Field(gt=1)
    rule: str


class StopRule(_Frozen):
    binding: bool
    P0: str
    P1: str
    P2: str
    P3: str
    means: str


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
    version_n: int = Field(ge=1000)          # muy por encima de los `n` de las versiones vivas
    exit: ExitSpec
    hypotheses: tuple[Hypothesis, ...]
    attempts: Attempts
    windows: Windows
    readings: tuple[Reading, ...]
    live_rule: LiveRule
    coverage: Coverage
    stages: tuple[Stage, ...]
    regression: Regression
    control: ControlSpec
    baseline: Baseline
    reading_rule: ReadingRule
    stop_rule: StopRule
    not_changed: str
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> Prereg:
        """Las cuentas que el pre-registro declara tienen que cuadrar entre sí."""
        a = self.attempts
        keys = sum(len(h.timeframes) for h in self.hypotheses)
        if a.new != keys:
            raise ValueError(f"claves nuevas: {a.new} ≠ {keys} estrategia@marco")
        if a.family != a.prior_keys + a.t137_keys + a.new:
            raise ValueError(f"familia de Holm: {a.family} ≠ "
                             f"{a.prior_keys} + {a.t137_keys} + {a.new}")
        if len({h.strategy for h in self.hypotheses}) != len(self.hypotheses):
            raise ValueError("hipótesis con la misma estrategia")
        if [r.id for r in self.readings if r.verdict] != ["oficial"]:
            raise ValueError("solo la lectura oficial puede dar veredicto")
        if self.windows.adjust.to != self.live_rule.alta:
            raise ValueError("la ventana de ajuste tiene que acabar en el alta")
        return self

    def hypothesis(self, strategy: str) -> Hypothesis:
        for h in self.hypotheses:
            if h.strategy == strategy:
                return h
        raise KeyError(f"{strategy} no es una hipótesis de {self.version}")

    def reading(self, rid: str) -> Reading:
        for r in self.readings:
            if r.id == rid:
                return r
        raise KeyError(f"{rid} no es una lectura de {self.version}")

    def sids(self) -> list[str]:
        """Las claves nuevas, en orden: estrategia@marco."""
        return [f"{h.strategy}@{tf}" for h in self.hypotheses for tf in h.timeframes]


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
                         f"versión nueva (prereg_t139_vN+1), no una edición. Huella: {digest}")
    out = Prereg(**data, sha256=digest)
    if strict and CRITERIA_PUBLISHED.get(out.criteria) != out.criteria_sha256:
        raise ValueError(f"{p.name} apunta a otros criterios que los publicados ({out.criteria})")
    return out
