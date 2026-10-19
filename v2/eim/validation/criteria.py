"""Criterios de la puerta de validación (T49): inmutables, cargados de un archivo versionado.

Mismo patrón que `eim/risk/config.py`: un cambio de umbral es un archivo NUEVO en
`eim/validation/versions/` (`validation_v2.json`, …), nunca se edita uno publicado. Además, el
hash de cada versión publicada queda fijado aquí (`PUBLISHED`): si alguien edita el archivo, la
carga falla. Así los criterios no se ajustan después de ver los resultados.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

VERSIONS_DIR = Path(__file__).parent / "versions"
DEFAULT_VERSION = "validation_v1"
# SHA-256 (fin de línea LF) de cada versión publicada. Solo se añaden entradas.
PUBLISHED: dict[str, str] = {
    "validation_v1": "0a5b19962ded0d12dfdbccac0359f91c1bebf211ed891f7817c96667e01c30a8",
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DataRule(_Frozen):                     # V1
    min_trades: int = Field(ge=1)
    min_regimes: int = Field(ge=1)
    min_per_regime: int = Field(ge=1)


class ExpectancyRule(_Frozen):               # V2
    boot_reps: int = Field(ge=1000)
    level: float = Field(gt=0.5, lt=1)


class RandomRule(_Frozen):                   # V3
    min_reps: int = Field(ge=100)
    reps_per_attempt: int = Field(ge=1)
    alpha: float = Field(gt=0, lt=0.5)


class DrawdownRule(_Frozen):                 # V4
    risk_per_trade: float = Field(gt=0, le=0.05)
    max_dd: float = Field(gt=0, lt=1)


class StabilityRule(_Frozen):                # V5
    window_days: int = Field(ge=1)
    window_min_trades: int = Field(ge=1)
    min_windows: int = Field(ge=1)
    min_positive_frac: float = Field(gt=0, le=1)
    live_min_trades: int = Field(ge=1)


class CostRule(_Frozen):                     # V6
    max_cost_r: float = Field(gt=0)


class NegativeRule(_Frozen):
    z: float = Field(ge=0)
    min_trades: int = Field(ge=2)


class Criteria(_Frozen):
    version: str
    description: str = ""
    scope: str = ""
    sha256: str = ""
    v1_data: DataRule
    v2_expectancy: ExpectancyRule
    v3_random: RandomRule
    v4_drawdown: DrawdownRule
    v5_stability: StabilityRule
    v6_costs: CostRule
    clear_negative: NegativeRule
    seed: int = 0
    notes: tuple[str, ...] = ()

    def null_reps(self, attempts: int) -> int:
        """Réplicas de lado aleatorio: suficientes para que Holm sobre `attempts` pueda pasar."""
        return max(self.v3_random.min_reps, self.v3_random.reps_per_attempt * max(attempts, 1))

    def to_json(self) -> dict:
        return self.model_dump(mode="json")


def file_hash(raw: bytes) -> str:
    # Hash sobre fin de línea LF: el mismo archivo da el mismo hash en todo equipo (T32).
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def load_criteria(version: str = DEFAULT_VERSION, path: str | Path | None = None) -> Criteria:
    """Lee y valida una versión de criterios; si está publicada, su hash debe coincidir."""
    p = Path(path) if path is not None else VERSIONS_DIR / f"{version}.json"
    raw = p.read_bytes()
    data = json.loads(raw)
    if data.get("version") != p.stem:
        raise ValueError(f"versión '{data.get('version')}' no coincide con el archivo {p.name}")
    digest = file_hash(raw)
    pinned = PUBLISHED.get(p.stem)
    if pinned is not None and pinned != digest:
        raise ValueError(f"{p.name} fue modificado después de publicarse: un cambio de umbral "
                         f"es una versión nueva (validation_vN+1), no una edición")
    return Criteria(**data, sha256=digest)
