"""Lista de vigilancia versionada (T64): canales, temas, idiomas, duración y presupuesto.

Inmutable: cambiar la lista = `versions/watchlist_vN.json` nuevo (lo vigila
`tests/test_param_versions.py`). Cada fila del catálogo guarda la versión y el hash con que se
vio o puntuó, así un cambio de lista nunca reescribe lo ya decidido.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSIONS = Path(__file__).resolve().parent / "versions"
DEFAULT = "watchlist_v1"

Permission = Literal["ninguno", "propio", "escrito"]
"""Permiso para transcribir (T62): `propio` = canal del usuario (captions.download de la API
oficial) · `escrito` = permiso escrito del autor · `ninguno` = solo metadatos, nunca a la cola."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Topic(_Frozen):
    name: str
    kind: Literal["asset", "macro"]
    asset: Literal["BTC", "ETH"] | None = None
    weight: float = Field(gt=0, le=1)
    keywords: tuple[str, ...] = Field(min_length=1)


class Channel(_Frozen):
    channel_id: str = Field(pattern=r"^UC[A-Za-z0-9_-]{22}$")
    name: str
    priority: int = Field(ge=1, le=5)
    languages: tuple[str, ...] = ()
    permission: Permission = "ninguno"
    verified: bool = False
    """True cuando el id se comprobó contra la API (los de ejemplo de v1 no lo están)."""


class Weights(_Frozen):
    topic: float = Field(ge=0)
    freshness: float = Field(ge=0)
    priority: float = Field(ge=0)

    @model_validator(mode="after")
    def _sum_one(self) -> Weights:
        if abs(self.topic + self.freshness + self.priority - 1.0) > 1e-9:
            raise ValueError("los pesos deben sumar 1")
        return self


class Budget(_Frozen):
    compute_hours_per_day: float = Field(gt=0)
    """Horas de cómputo por día UTC que la cola puede admitir (T62: ≈ 95 videos de 20 min por
    noche sin VLM; aquí se deja holgura)."""
    compute_ratio: float = Field(gt=0)
    """Segundos de cómputo estimados por segundo de video (T62: ASR ×0,15–0,18 + margen)."""
    quota_units_per_day: int = Field(gt=0)
    """Unidades de la Data API v3 que el EIM se permite gastar por día UTC (de las 10 000 por
    defecto del proyecto de Google del usuario)."""
    max_pages_per_channel: int = Field(ge=1)
    backfill_max_pages: int = Field(ge=1)


class Watchlist(_Frozen):
    version: str
    created: str
    note: str = ""
    languages: tuple[str, ...] = Field(min_length=1)
    duration_min_s: int = Field(ge=0)
    duration_max_s: int = Field(gt=0)
    freshness_half_life_h: float = Field(gt=0)
    threshold: float = Field(ge=0, le=1)
    weights: Weights
    budget: Budget
    rss_enabled: bool = False
    topics: tuple[Topic, ...] = Field(min_length=1)
    channels: tuple[Channel, ...] = Field(min_length=1)
    hash: str = ""
    """SHA-256 del archivo (LF); lo rellena `load`, no se escribe en el JSON."""

    @model_validator(mode="after")
    def _check(self) -> Watchlist:
        if self.duration_min_s >= self.duration_max_s:
            raise ValueError("duración mínima ≥ máxima")
        ids = [c.channel_id for c in self.channels]
        if len(ids) != len(set(ids)):
            raise ValueError("canal repetido")
        for t in self.topics:
            if (t.kind == "asset") != (t.asset is not None):
                raise ValueError(f"tema {t.name}: `asset` solo y siempre en temas de activo")
        return self

    def channel(self, channel_id: str) -> Channel | None:
        return next((c for c in self.channels if c.channel_id == channel_id), None)


def file_hash(raw: bytes) -> str:
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def load(name: str = DEFAULT, directory: Path = VERSIONS) -> Watchlist:
    raw = (directory / f"{name}.json").read_bytes()
    wl = Watchlist.model_validate_json(raw)
    if wl.version != name.removeprefix("watchlist_"):
        raise ValueError(f"{name}: la versión interna es {wl.version!r}")
    return wl.model_copy(update={"hash": file_hash(raw)})
