"""Ficha común de bot (T56) como modelo inmutable y carga validada del catálogo.

El esquema vive en `eim/bots/registry/SCHEMA.md`; aquí se hace cumplir. Una ficha que no valida
(campo de más, de menos, `id` distinto del archivo, `enabled` incoherente) no entra al escuadrón.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REGISTRY = Path(__file__).resolve().parent / "registry"
SECURITY_THRESHOLD = 70  # `enabled = sin alertas rojas y total ≥ 70` (SCHEMA.md)


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class License(_M):
    spdx: str  # «NONE» si no hay archivo de licencia (un badge del README no cuenta)
    file: str | None
    sha256: str | None
    head: str | None

    @model_validator(mode="after")
    def _none_means_no_file(self) -> License:
        if (self.spdx == "NONE") != (self.file is None):
            raise ValueError("spdx «NONE» exactamente cuando no hay archivo de licencia")
        return self


class Strategy(_M):
    name: str
    path: str
    note: str


class Approval(_M):
    state: Literal["pendiente", "aprobada"]
    by: str | None
    at: str | None


class Operational(_M):
    checks: dict[str, int]
    total: int
    tests_files: int
    days_since_commit: int


class Security(_M):
    checks: dict[str, bool]
    notes: dict[str, str]
    red_alerts: list[str]
    total: int
    enabled: bool

    @model_validator(mode="after")
    def _enabled_rule(self) -> Security:
        if self.enabled != (not self.red_alerts and self.total >= SECURITY_THRESHOLD):
            raise ValueError("`enabled` no sigue la regla (sin alertas rojas y total ≥ 70)")
        return self


class Evidence(_M):
    what: str
    url: str


class BotCard(_M):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    repo: str
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    commit_date: str
    audited_at: str
    license: License
    bot_class: Literal["D", "L", "IA", "INFRA"]
    integration_mode: Literal["A", "B", "C", "D"]
    binance_markets: list[Literal["spot", "usdm_futures"]]
    strategies: list[Strategy]
    dependencies: list[str]
    risks: list[str]
    reasons: list[str]
    verdict: Literal["usar", "referencia", "descartar"]
    squad_proposal: Literal["propuesto", "opcional", "no"]
    approval: Approval
    operational: Operational
    security: Security
    evidence: list[Evidence]
    audit_scope: str
    universe_ref: int | None

    @property
    def usable(self) -> bool:
        """Puede entrar al escuadrón: seguridad habilitada y aprobada por el usuario (◆)."""
        return self.security.enabled and self.approval.state == "aprobada"


def load_cards(root: Path | None = None) -> dict[str, BotCard]:
    """Todas las fichas del catálogo, validadas. Falla ruidosamente si alguna no cumple."""
    cards: dict[str, BotCard] = {}
    for path in sorted((root or REGISTRY).glob("*.json")):
        card = BotCard.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if card.id != path.stem:
            raise ValueError(f"{path.name}: el id «{card.id}» no coincide con el archivo")
        cards[card.id] = card
    return cards


@lru_cache(maxsize=1)
def default_cards() -> dict[str, BotCard]:
    return load_cards()


def card_of(bot_id: str) -> BotCard:
    try:
        return default_cards()[bot_id]
    except KeyError:
        raise KeyError(f"bot sin ficha en el catálogo: {bot_id}") from None
