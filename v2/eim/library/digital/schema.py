"""Esquemas de la biblioteca digital (T151): referencias consultables en línea y fichas extraídas.

Una referencia digital NO es un libro del usuario: es una obra localizada en un repositorio legítimo
(DOI, arXiv, sitio oficial). Sus datos bibliográficos salen del registro (OpenAlex/Crossref/arXiv),
no de la memoria de quien la catalogó: lo curado a mano (categoría, conceptos, postura) va aparte
y marcado como tal. Nunca se declara leído un texto que no se pudo descargar: `coverage` dice qué
se leyó de verdad (metadatos, resumen o texto completo).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ID_PATTERN = r"^[a-z][a-z0-9_]*$"
MAX_FRAGMENT_WORDS = 25

Category = Literal["A", "B", "C", "D", "E", "F", "G", "H"]
CATEGORY_NAMES: dict[str, str] = {
    "A": "Análisis técnico avanzado", "B": "Trading cuantitativo y estadístico",
    "C": "Gestión del riesgo y del capital", "D": "Psicología y comportamiento del mercado",
    "E": "Estrategias intradía y scalping", "F": "Criptomonedas y mercados de futuros",
    "G": "Inteligencia artificial aplicada", "H": "Macrofinanzas y contexto económico",
}
# Acceso: abierto = licencia abierta o repositorio; gratuito = lectura libre sin licencia abierta;
# suscripcion = de pago o restringido. «vista_previa» solo si alguien lo comprobó a mano.
Access = Literal["abierto", "gratuito", "vista_previa", "suscripcion", "desconocido"]
# Qué hay disponible para leer de verdad, según la última verificación.
Availability = Literal["texto_completo", "solo_resumen", "solo_metadatos", "pendiente"]
Reliability = Literal["alta", "media", "baja"]
DocType = Literal["articulo", "preprint", "libro", "capitulo", "informe", "curso", "otro"]
# Nivel de la afirmación (T152): nunca se convierte una teoría en regla operativa sin pruebas.
EvidenceLevel = Literal["teoria", "hipotesis", "estrategia_documentada", "evidencia_empirica",
                        "validada_eim"]
StanceKind = Literal["apoya", "objeta", "condiciona"]
Coverage = Literal["metadatos", "resumen", "texto_completo"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Stance(_Frozen):
    """Postura de una obra frente a un concepto de la taxonomía (curada, comprobable).

    `terms` son palabras que deben aparecer en el resumen o texto descargado para que la postura
    cuente como verificada (`python -m eim.library digital verify`); `conditions` dice en qué
    mercado/horizonte la encontró el autor.
    """

    concept: str = Field(pattern=ID_PATTERN)
    kind: StanceKind
    level: EvidenceLevel
    summary: str = Field(min_length=1, max_length=280)
    conditions: str = Field(default="", max_length=200)
    terms: list[str] = Field(default=[], max_length=6)


class Curated(_Frozen):
    """Lo que añade quien cataloga (marcado `curado`, no viene del registro)."""

    category: Category
    concepts: list[str] = Field(min_length=1)
    methods: list[str] = []
    description: str = Field(min_length=1, max_length=400)
    application: str = Field(min_length=1, max_length=280)
    stances: list[Stance] = []
    reliability: Reliability | None = None        # None → se deduce del tipo de obra
    markets: list[str] = []                         # dónde se estudió (cripto, acciones, FX...)


class Locator(_Frozen):
    """Cómo encontrar la obra: DOI, arXiv o una URL oficial (al menos uno)."""

    doi: str | None = None
    arxiv: str | None = None
    url: str | None = None
    expect: str = Field(min_length=3, max_length=120)   # fragmento del título esperado
    # Solo para obras web sin registro (curso, informe, libro libre): metadatos curados.
    web: dict | None = None

    @model_validator(mode="after")
    def _one(self) -> Locator:
        if not (self.doi or self.arxiv or self.url):
            raise ValueError("una referencia necesita DOI, arXiv o URL")
        return self


class SeedRef(_Frozen):
    """Entrada de `seed.json` (curada a mano)."""

    id: str = Field(pattern=ID_PATTERN)
    locator: Locator
    curated: Curated


class Verified(_Frozen):
    """Datos bibliográficos tal como los devolvió el registro en la última verificación."""

    title: str
    authors: list[str]
    year: int | None = None
    venue: str | None = None
    publisher: str | None = None
    doc_type: DocType
    url: str                       # página oficial de consulta
    oa_url: str | None = None      # texto completo legal, si existe
    access: Access
    availability: Availability
    source: str                    # «openalex», «arxiv», «web»
    verified_at: str               # fecha ISO de la última verificación
    cited_by: int | None = None
    has_abstract: bool = False


class DigitalRef(_Frozen):
    """Entrada de `catalog.json`: curado + verificado (o el motivo por el que no se verificó)."""

    id: str = Field(pattern=ID_PATTERN)
    locator: Locator
    curated: Curated
    verified: Verified | None = None
    problem: str | None = None

    @property
    def ok(self) -> bool:
        return self.verified is not None and self.problem is None

    @property
    def reliability(self) -> Reliability:
        if self.curated.reliability:
            return self.curated.reliability
        t = self.verified.doc_type if self.verified else "otro"
        return {"articulo": "alta", "libro": "media", "capitulo": "media", "informe": "media",
                "curso": "media", "preprint": "media"}.get(t, "baja")


class Fragment(_Frozen):
    """Fragmento literal ≤ 25 palabras de lo descargado (resumen o texto), con su origen."""

    text: str
    where: Coverage

    @model_validator(mode="after")
    def _short(self) -> Fragment:
        if len(self.text.split()) > MAX_FRAGMENT_WORDS:
            raise ValueError(f"un fragmento no puede pasar de {MAX_FRAGMENT_WORDS} palabras")
        return self


class DigitalCard(_Frozen):
    """Ficha de conocimiento extraída de una referencia digital (T152)."""

    ref_id: str = Field(pattern=ID_PATTERN)
    coverage: Coverage
    concepts: list[str]
    methods: list[str]
    conditions: list[str]          # condiciones de mercado mencionadas (tendencia, rango...)
    limitations: list[Fragment]
    findings: list[Fragment]
    level: EvidenceLevel
    stances_verified: list[str]    # conceptos cuya postura se comprobó en el texto
    stances_pending: list[str]
    operational_rules: list[str] = []   # solo si la obra las define con umbrales explícitos
    extracted_at: str
