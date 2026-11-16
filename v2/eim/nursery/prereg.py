"""Pre-registro `cantera_v1` (T170): inmutable, con su huella fijada aquí. SIMULADO.

Congela, antes de la primera operación de la cantera, la familia (qué prospectos entran, con qué
huella, banda, tema y hermano simple), las cuentas (capital, riesgo, puerta de costo), los
controles, la medida y su vara contra la suerte, el escalafón con todos sus umbrales
(`ladder_rules.LadderRules`), las plazas de reserva y el reloj. Patrón de T137/T139: cambiar
cualquier valor es un archivo nuevo (`prereg_cantera_v2.json`) **con reloj nuevo**, nunca una
edición; si alguien edita el publicado, la carga falla con el motivo.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eim.nursery.ladder import Member
from eim.nursery.ladder_rules import LadderRules
from eim.nursery.prospect import Prospect
from eim.validation.criteria import PUBLISHED as CRITERIA_PUBLISHED
from eim.validation.criteria import file_hash

PREREG_DIR = Path(__file__).resolve().parents[1] / "validation" / "prereg"
DEFAULT_VERSION = "prereg_cantera_v1"
# SHA-256 (fin de línea LF) de cada versión publicada. Solo se añaden entradas.
PUBLISHED: dict[str, str] = {
    "prereg_cantera_v1": "fc3001f980a3d67b0f872de0d5b4eca1f0def81dafeb9b1268b894df2f52fd92",
}
THEMES = ("tendencia", "reversion", "derivados", "consenso")
BANDS = ("scalping", "intradia", "tres_dias", "semanal")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MemberSpec(_Frozen):
    id: str
    fingerprint: str
    agent_id: str
    timeframe: Literal["15m", "1h", "4h"]
    role: Literal["base", "candidato"]
    n_params: int = Field(ge=0, le=3)
    band: Literal["scalping", "intradia", "tres_dias", "semanal"]
    band_source: Literal["medida_t169", "medida_t170", "declarada"]
    history: bool
    theme: Literal["tendencia", "reversion", "derivados", "consenso"]
    sibling: str | None = None
    generic: str
    expected_in_term: int | None = None


class Discarded(_Frozen):
    id: str
    fingerprint: str
    stage: Literal["examen_fisico_t169"]
    reason: str


class Family(_Frozen):
    kind: Literal["propia"]
    why: str
    enrolled_t167: int = Field(ge=1)
    reserve_slots: int = Field(ge=0)
    ceiling: int = Field(ge=1)
    m: int = Field(ge=1)
    m_rule: str
    members: tuple[MemberSpec, ...]
    discarded: tuple[Discarded, ...]
    redesigned: tuple[str, ...]

    @model_validator(mode="after")
    def _counts(self) -> Family:
        ids = [x.id for x in self.members] + [x.id for x in self.discarded]
        if len(set(ids)) != len(ids):
            raise ValueError("un prospecto aparece dos veces en la familia")
        if len(ids) != self.enrolled_t167:
            raise ValueError(f"{len(ids)} prospectos ≠ {self.enrolled_t167} inscritos en T167")
        if self.ceiling != self.enrolled_t167 + self.reserve_slots:
            raise ValueError("techo ≠ inscritos + plazas de reserva")
        if self.m != len(self.members) + self.reserve_slots:
            raise ValueError("m de e-BH ≠ los que entran + las plazas de reserva")
        mids = {x.id for x in self.members}
        bad = [x.id for x in self.members if x.sibling and x.sibling not in mids]
        if bad or not set(self.redesigned) <= mids | {x.id for x in self.discarded}:
            raise ValueError(f"hermanos o rediseños fuera de la familia: {bad}")
        return self


class Accounts(_Frozen):
    initial_equity_usdt: float = Field(gt=0)
    risk_pct: float = Field(gt=0, le=0.02)
    cost_gate_max_r: float = Field(gt=0)
    twins_k: int = Field(ge=1)
    seed: int
    execution: str
    not_adapted: str


class Clock(_Frozen):
    not_before_utc: str
    alta: str
    reviews: str
    deadline: str
    stop_rule: str
    change_rule: str


class Prereg(_Frozen):
    version: str
    sha256: str = ""
    declared: str
    description: str
    mode: Literal["SIMULADO"]
    symbol: Literal["BTCUSDT"]
    criteria: str
    criteria_sha256: str
    decisions: tuple[str, ...]
    family: Family
    accounts: Accounts
    controls: tuple[str, ...]
    measure: dict[str, str | list[str]]
    bands: dict[str, str]
    ladder: LadderRules
    false_promises: dict
    reserve: tuple[str, ...]
    clock: Clock
    self_improvement: tuple[str, ...]
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _coherent(self) -> Prereg:
        mids = {x.id for x in self.family.members}
        if set(self.ladder.drawdown.caps_pct) != mids:
            raise ValueError("cada prospecto que entra lleva su tope de drawdown calibrado")
        if abs(self.accounts.risk_pct - self.ladder.drawdown.risk_pct) > 1e-12:
            raise ValueError("el tope de drawdown se calibró con otro riesgo por operación")
        if self.ladder.forward_exam.max_cost_r != self.accounts.cost_gate_max_r:
            raise ValueError("el examen hacia adelante y la puerta de costo usan varas distintas")
        return self

    def members(self) -> tuple[Member, ...]:
        return tuple(Member(x.id, x.agent_id, x.timeframe, x.n_params, x.band, x.history,
                            x.theme, x.sibling, x.generic) for x in self.family.members)

    @property
    def m(self) -> int:
        return self.family.m


def load_prereg(version: str = DEFAULT_VERSION, path: str | Path | None = None,
                strict: bool = True) -> Prereg:
    """Lee y valida una versión; si está publicada, su huella y la de sus criterios deben coincidir.

    `strict=False` solo lo usan las pruebas con un pre-registro de juguete.
    """
    p = Path(path) if path is not None else PREREG_DIR / f"{version}.json"
    raw = p.read_bytes()
    data = json.loads(raw)
    if data.get("version") != p.stem:
        raise ValueError(f"versión '{data.get('version')}' no coincide con el archivo {p.name}")
    digest = file_hash(raw)
    pinned = PUBLISHED.get(p.stem)
    if strict and pinned and pinned != digest:
        raise ValueError(f"{p.name} fue modificado después de publicarse: cualquier cambio es "
                         f"`cantera_v2` con reloj nuevo, no una edición. Huella: {digest}")
    if strict and pinned == "":
        raise ValueError(f"{p.name} no tiene huella fijada en el código (PUBLISHED)")
    out = Prereg(**data, sha256=digest)
    if strict and CRITERIA_PUBLISHED.get(out.criteria) != out.criteria_sha256:
        raise ValueError(f"{p.name} apunta a otros criterios que los publicados ({out.criteria})")
    return out


def not_before_ms(pr: Prereg) -> int:
    """`clock.not_before_utc` (p. ej. «2026-11-16T22:00Z») en ms."""
    from datetime import datetime

    raw = pr.clock.not_before_utc.replace("Z", "+00:00")
    return int(datetime.fromisoformat(raw).timestamp() * 1000)


def family_prospects(pr: Prereg, prospects: Sequence[Prospect]) -> tuple[Prospect, ...]:
    """Los prospectos que entran, en el orden del pre-registro, con la huella congelada.

    Falla si falta alguno o si su huella cambió: un prospecto con otra huella es otro prospecto
    y no está pre-registrado.
    """
    by = {p.id: p for p in prospects}
    out, bad = [], []
    for x in pr.family.members:
        p = by.get(x.id)
        if p is None or p.fingerprint != x.fingerprint:
            bad.append(f"{x.id} (pre-registro {x.fingerprint}, código "
                       f"{p.fingerprint if p else 'ausente'})")
        else:
            out.append(p)
    if bad:
        raise ValueError("la cantera no coincide con su pre-registro: " + "; ".join(bad))
    return tuple(out)
