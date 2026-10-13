"""Salida estructurada del LLM (validada con pydantic) y su esquema JSON para la API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Claim(BaseModel):
    """Afirmación/catalizador con la fuente (id de titular) que la respalda."""

    model_config = ConfigDict(frozen=True)

    texto: str = Field(min_length=1, max_length=300)
    fuente: str  # id de un titular entregado; sin fuente válida → se descarta


class ContextOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    tema: str = Field(max_length=200)
    sentimiento: float = Field(ge=-1, le=1)
    catalizadores: list[Claim] = []
    riesgo_evento: Literal["bajo", "medio", "alto"]
    fuentes: list[str] = []
