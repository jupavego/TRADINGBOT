"""Pre-registro del banco de salidas (T131): archivo inmutable con huella, como los criterios T49.

Mismo patrón que `eim/validation/criteria.py` y `eim/risk/config.py`: cambiar un umbral, un tramo
o un valor de la rejilla es un archivo NUEVO en `versions/` (`prereg_t131_v2.json`, …), nunca una
edición de uno publicado. Además el SHA-256 de cada versión publicada queda fijado aquí
(`PUBLISHED`): si alguien edita el archivo, la carga falla con el motivo. Así la rejilla, los
tramos, el objetivo de selección y los criterios no se pueden ajustar después de ver los
resultados, que es justo lo que T131 tiene que impedir.

`attempts()` cuenta TODOS los intentos de la rejilla —también las variantes que T132 y T133 aún no
han implementado— porque entran en el Sharpe deflactado y en las correcciones por pruebas
múltiples: lo que se prueba cuenta aunque se pruebe más tarde.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from eim.validation.criteria import file_hash

VERSIONS_DIR = Path(__file__).parent / "versions"
DEFAULT_VERSION = "prereg_t131_v2"
# SHA-256 (fin de línea LF) de cada versión publicada. Solo se añaden entradas.
# v2 corrige la definición de la meseta (sobre LA MEJORA frente a la base, como dice §5.3 de
# `PLAN/notas/T129_sl_dinamico.md`, no sobre el E[R] absoluto); v1 queda publicada e intacta.
PUBLISHED: dict[str, str] = {
    "prereg_t131_v1": "730a11f987e65e0835aa9e4090a7d62005be60fd582953f6113605fa27bc9c73",
    "prereg_t131_v2": "0dd3d9d8550beac024ac71f5d33c52f45da31b7526bf7e1844df98af117e64f0",
}
IMPLEMENTED = "implementada"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Design(_Frozen):
    start: str
    end: str
    reserve_note: str = ""
    path_timeframe: str
    fine_timeframe: str
    decision_timeframes: tuple[str, ...]
    fit_months: int = Field(ge=1)
    test_months: int = Field(ge=1)
    step_months: int = Field(ge=1)
    embargo_quantile: float = Field(gt=0.5, lt=1)
    embargo_feature_hours: float = Field(ge=0)


class Bootstrap(_Frozen):
    block: str
    reps: int = Field(ge=1000)
    level: float = Field(gt=0.5, lt=1)


class Multiple(_Frozen):
    primary: str
    reference: str
    reps: int = Field(ge=1000)
    alpha: float = Field(gt=0, lt=0.5)


class Pbo(_Frozen):
    splits: int = Field(ge=4)
    max_pbo: float = Field(gt=0, lt=1)


class Selection(_Frozen):
    objective: str
    constraints: tuple[str, ...]
    base: str
    choose: str
    plateau_keep: float = Field(gt=0, le=1)


class CostStress(_Frozen):
    stop_slip_multipliers: tuple[float, ...]
    approve_at: float = Field(ge=1)


class Control(_Frozen):
    strategy: str
    expect: str


class Ruin(_Frozen):
    risk_pct: float = Field(gt=0, le=0.05)
    trades: int = Field(ge=1)
    reps: int = Field(ge=1)
    floor: float = Field(gt=0, lt=1)


class Accept(_Frozen):
    bases: tuple[str, ...]
    delta_ci_lower_above: float
    win_loss_ratio_min: float = Field(gt=0)
    pf_vs_base_min: float = Field(ge=1)
    max_dd_vs_base_max: float = Field(ge=1)
    cvar_not_worse: bool
    folds_positive_frac_min: float = Field(gt=0, le=1)
    years: tuple[int, ...]
    plateau_keep: float = Field(gt=0, le=1)
    pbo_max: float = Field(gt=0, lt=1)
    prospective_weeks_min: int = Field(ge=1)


class GridItem(_Frozen):
    id: str
    family: str
    status: str
    params: dict[str, tuple]
    note: str = ""

    @property
    def combos(self) -> int:
        return math.prod(len(v) for v in self.params.values()) if self.params else 1


class Prereg(_Frozen):
    version: str
    description: str = ""
    scope: str = ""
    sha256: str = ""
    symbol: str
    seed: int
    risk_usd: float = Field(gt=0)
    design: Design
    bootstrap: Bootstrap
    multiple: Multiple
    pbo: Pbo
    selection: Selection
    cost_stress: CostStress
    control: Control
    ruin: Ruin
    accept: Accept
    grid: tuple[GridItem, ...]
    notes: tuple[str, ...] = ()

    def attempts(self) -> int:
        """Intentos pre-registrados: la rejilla entera, implementada o no (E12 y Sharpe
        deflactado)."""
        return sum(g.combos for g in self.grid)

    def implemented(self) -> tuple[str, ...]:
        return tuple(g.id for g in self.grid if g.status == IMPLEMENTED)

    def pending(self) -> dict[str, str]:
        """Variantes aún sin implementar y la tarea que las trae."""
        return {g.id: g.status for g in self.grid if g.status != IMPLEMENTED}

    def item(self, pid: str) -> GridItem:
        for g in self.grid:
            if g.id == pid:
                return g
        raise KeyError(f"{pid} no está en la rejilla pre-registrada de {self.version}")

    def to_json(self) -> dict:
        return self.model_dump(mode="json")


def load_prereg(version: str = DEFAULT_VERSION, path: str | Path | None = None,
                strict: bool = True) -> Prereg:
    """Lee y valida una versión del pre-registro; si está publicada, su hash debe coincidir.

    `strict=False` solo lo usan las pruebas que construyen un pre-registro de juguete: en el
    código de producción un archivo publicado y modificado tiene que fallar.
    """
    p = Path(path) if path is not None else VERSIONS_DIR / f"{version}.json"
    raw = p.read_bytes()
    data = json.loads(raw)
    if data.get("version") != p.stem:
        raise ValueError(f"versión '{data.get('version')}' no coincide con el archivo {p.name}")
    digest = file_hash(raw)
    pinned = PUBLISHED.get(p.stem)
    if strict and pinned is not None and pinned != digest:
        raise ValueError(f"{p.name} fue modificado después de publicarse: un cambio de rejilla, "
                         f"tramo o criterio es una versión nueva (prereg_t131_vN+1), no una "
                         f"edición. Huella del archivo: {digest}")
    return Prereg(**data, sha256=digest)
