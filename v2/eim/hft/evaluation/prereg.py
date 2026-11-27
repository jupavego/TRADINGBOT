"""Pre-registro de la prueba de techo (T80): inmutable y con huella, como T49, T137 y T139.

Cambiar un umbral, una ventana, un horizonte o la regla de veredicto es un archivo NUEVO en
`eim/hft/prereg/`, nunca una edición del publicado: el SHA-256 queda fijado aquí y la carga falla
si alguien lo toca. Así los criterios no se ajustan después de ver los resultados.

La cuenta de la familia de Holm se comprueba al cargar y al medir: si el número de intentos que
calcula el código no es el declarado, el informe no se escribe.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eim.validation.criteria import file_hash

PREREG_DIR = Path(__file__).parent.parent / "prereg"
DEFAULT_VERSION = "hft_ceiling_v1"
# SHA-256 (fin de línea LF) de cada versión publicada. Solo se añaden entradas.
PUBLISHED: dict[str, str] = {
    "hft_ceiling_v1": "a5dbd8e56540191da14724b9e2b6902676f369e27edc557dfd77782d7edfd5c0",
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow", populate_by_name=True)


class DataSpec(_Frozen):
    symbol: str
    from_: str = Field(alias="from")
    to: str
    step_ms: int = Field(gt=0)
    levels: int = Field(ge=1)
    min_days: int = Field(ge=1)
    min_rows_per_day: int = Field(ge=1)


class Split(_Frozen):
    train_days: int = Field(ge=1)
    test_days: int = Field(ge=1)
    embargo_days: int = Field(ge=0)
    min_test_days: int = Field(ge=1)


class Signals(_Frozen):
    features: int = Field(ge=1)
    baseline: int = Field(ge=0)
    ridge: int = Field(ge=0)


class Attempts(_Frozen):
    family: int = Field(ge=1)
    rule: str
    registry: str = ""


class Metrics(_Frozen):
    boot_reps: int = Field(ge=1000)
    level: float = Field(gt=0.5, lt=1)
    seed: int = 0


class Reaction(_Frozen):
    p50_ms: int = Field(ge=0)
    p99_ms: int = Field(ge=0)
    used_ms: int = Field(ge=0)


class Prereg(_Frozen):
    version: str
    task: str
    description: str = ""
    sha256: str = ""
    data: DataSpec
    horizons_s: tuple[int, ...]
    reaction: Reaction
    costs_bps: dict[str, float]
    split: Split
    signals: Signals
    attempts: Attempts
    metrics: Metrics
    gates: dict[str, dict]
    verdict_rule: dict[str, str]
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _family(self) -> Prereg:
        s = self.signals
        want = (s.features + s.baseline + s.ridge) * len(self.horizons_s)
        if want != self.attempts.family:
            raise ValueError(f"familia de Holm declarada {self.attempts.family} ≠ {want} "
                             "(señales × horizontes)")
        return self

    @property
    def n_signals(self) -> int:
        return self.signals.features + self.signals.baseline + self.signals.ridge

    def gate(self, key: str) -> dict:
        return self.gates[key]

    def threshold(self, key: str, field: str = "threshold") -> float:
        return float(self.gates[key][field])


def load_prereg(version: str = DEFAULT_VERSION, path: str | Path | None = None) -> Prereg:
    """Lee y valida una versión del pre-registro; si está publicada, su hash debe coincidir."""
    p = Path(path) if path is not None else PREREG_DIR / f"{version}.json"
    raw = p.read_bytes()
    digest = file_hash(raw)
    pinned = PUBLISHED.get(p.stem)
    if pinned is not None and pinned != digest:
        raise ValueError(f"{p.name} fue modificado después de publicarse: un cambio de criterio "
                         "es una versión nueva (hft_ceiling_vN+1), no una edición")
    data = json.loads(raw)
    if data.get("version") != p.stem:
        raise ValueError(f"versión '{data.get('version')}' no coincide con el archivo {p.name}")
    return Prereg(**data, sha256=digest)
