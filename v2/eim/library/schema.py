"""Esquemas de la biblioteca de trading (T52): ficha de conocimiento y entrada del catálogo.

Una ficha (`KnowledgeCard`) es una **hipótesis** tomada de un libro, parafraseada y citada; nunca
evidencia. Guardas de derechos de autor en el propio esquema: `claim` ≤ 400 caracteres y `quote`
≤ 25 palabras. Una ficha `verificada_en_texto` tiene al menos una cita con página; lo que venga
del conocimiento general sin página localizada queda `pendiente`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_CLAIM_CHARS = 400
MAX_QUOTE_WORDS = 25
ID_PATTERN = r"^[a-z][a-z0-9_]*$"

Kind = Literal["regla", "patron", "principio", "gestion_riesgo", "psicologia", "advertencia"]
Status = Literal["borrador", "revisada_usuario", "codificada", "descartada"]
Verification = Literal["verificada_en_texto", "pendiente"]
License = Literal["propia", "dominio_publico", "acceso_abierto"]
Direction = Literal["alcista", "bajista", "giro", "continuacion", "neutral", "segun_contexto"]
Relation = Literal["apoya", "contradice", "complementa"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Condition(_Frozen):
    """Condición operacionalizable: qué se mide, con qué regla, umbral, marco y confirmación."""

    indicator: str = Field(min_length=1, max_length=80)
    rule: str = Field(min_length=1, max_length=240)
    threshold: str | None = Field(default=None, max_length=80)
    timeframe: str | None = Field(default=None, max_length=60)
    confirmation: str | None = Field(default=None, max_length=200)


class ExpectedEffect(_Frozen):
    """Efecto que el autor espera. Horizonte y magnitud solo si el autor los da."""

    direction: Direction
    horizon: str | None = Field(default=None, max_length=120)
    magnitude: str | None = Field(default=None, max_length=160)


class Citation(_Frozen):
    """Cita: libro del catálogo, capítulo y páginas del archivo (1 = primera página del PDF).

    `terms` son palabras del pasaje que deben aparecer en esas páginas (comprobación mecánica
    con `python -m eim.library verify`, sin copiar el texto); `printed` es la página impresa si
    difiere de la del archivo.
    """

    book_id: str = Field(pattern=ID_PATTERN)
    chapter: str = Field(min_length=1, max_length=120)
    pages: list[int] = Field(min_length=1)
    printed: str | None = Field(default=None, max_length=40)
    terms: list[str] = Field(default=[], max_length=6)

    @field_validator("pages")
    @classmethod
    def _pages_positive(cls, v: list[int]) -> list[int]:
        if any(p < 1 for p in v):
            raise ValueError("las páginas empiezan en 1")
        return v


class Applicability(_Frozen):
    """Dónde la planteó el autor y el supuesto explícito para cripto 24/7."""

    original_market: list[str] = Field(min_length=1)
    timeframe: str = Field(min_length=1, max_length=80)
    crypto_24_7: str = Field(min_length=1, max_length=240)


class RelatedCard(_Frozen):
    id: str = Field(pattern=ID_PATTERN)
    relation: Relation


class KnowledgeCard(_Frozen):
    id: str = Field(pattern=ID_PATTERN)
    title: str = Field(min_length=1, max_length=120)
    kind: Kind
    claim: str = Field(min_length=1, max_length=MAX_CLAIM_CHARS)
    conditions: list[Condition] = []
    expected_effect: ExpectedEffect | None = None
    author_evidence: str = Field(min_length=1, max_length=240)
    citations: list[Citation] = []
    quote: str | None = None
    applicability: Applicability
    testable: bool
    status: Status = "borrador"
    verification: Verification
    related: list[RelatedCard] = []

    @field_validator("quote")
    @classmethod
    def _short_quote(cls, v: str | None) -> str | None:
        if v is not None and len(v.split()) > MAX_QUOTE_WORDS:
            raise ValueError(f"la cita textual supera {MAX_QUOTE_WORDS} palabras")
        return v

    @model_validator(mode="after")
    def _verified_needs_page(self) -> KnowledgeCard:
        if self.verification == "verificada_en_texto" and not self.citations:
            raise ValueError("una ficha verificada_en_texto necesita al menos una cita con página")
        if self.quote and not self.citations:
            raise ValueError("una cita textual necesita su página")
        if self.testable and not self.conditions:
            raise ValueError("una ficha comprobable necesita condiciones operacionalizables")
        return self

    @property
    def book_ids(self) -> set[str]:
        return {c.book_id for c in self.citations}


class CardFile(_Frozen):
    """Contenido de `eim/library/cards/<book_id>.json` (`book_id=None` → fichas entre autores)."""

    book_id: str | None = None
    cards: list[KnowledgeCard]


class BookMeta(_Frozen):
    """Metadatos conocidos de un libro (registro versionado `eim/library/books.json`)."""

    id: str = Field(pattern=ID_PATTERN)
    title: str
    author: str
    year: int | None = None
    edition: str | None = None
    language: str = "en"
    license: License = "propia"
    match: list[str] = []          # fragmentos del nombre de archivo (minúsculas)
    pages: int | None = None       # páginas esperadas (para validar citas sin el índice local)


class CatalogEntry(_Frozen):
    """Entrada de `index/catalog.json` (local, no versionado)."""

    id: str
    title: str
    author: str
    year: int | None
    edition: str | None
    language: str
    format: Literal["pdf", "epub"]
    pages: int
    pages_with_text: int
    pages_ocr: int
    pages_flagged: list[int] = []   # páginas con texto dirigido a un modelo (dato, no instrucción)
    sha256: str
    license: License
    path: str
    status: Literal["ok", "parcial", "sin_texto"]
    reason: str | None = None
    ingested_at: str
