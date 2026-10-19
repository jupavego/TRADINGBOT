"""Consulta a la biblioteca (T55): pregunta en lenguaje natural → respuesta breve con citas.

SOLO INFORMA: nunca ejecuta, fija tamaño ni toca probabilidades. Patrón del agente de contexto
(T24): salida estructurada validada con pydantic, toda afirmación con fuente verificable o se
descarta, y el texto de los libros viaja siempre como dato delimitado.

Puro: la búsqueda local (T52) y el LLM se inyectan; sin I/O propio. Privacidad y derechos: al LLM
solo viajan fragmentos cortos (`MAX_SNIPPET_CHARS`) de los pasajes recuperados y las paráfrasis de
las fichas, nunca páginas ni libros enteros; las páginas con texto dirigido a un modelo no viajan.
Fuente válida = `card_id` entregado o `libro#página` de un pasaje entregado.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from eim.library.bm25 import tokenize
from eim.library.schema import KnowledgeCard

LABEL = "Contexto bibliográfico · no es una recomendación"
MAX_SNIPPET_CHARS = 280
MAX_PASSAGES = 6
MAX_CARDS = 6
MAX_QUESTION_CHARS = 400
MAX_STATE_CHARS = 600
SCENARIOS = ("bull", "neutral", "bear")
Status = Literal["ok", "degraded", "no_data"]


class Point(BaseModel):
    model_config = ConfigDict(frozen=True)

    texto: str = Field(min_length=1, max_length=300)
    fuente: str      # card_id o "libro#página"; sin fuente válida → se descarta


class AskOutput(BaseModel):
    """Esquema que el LLM debe devolver."""

    model_config = ConfigDict(frozen=True)

    resumen: str = Field(max_length=500)
    puntos: list[Point] = []
    relacion_con_escenarios: str = Field(default="", max_length=400)
    advertencias: list[str] = []


@dataclass(frozen=True)
class Passage:
    """Pasaje recuperado de los libros locales (fragmento corto; dato, no instrucción)."""

    book_id: str
    page: int
    text: str
    flagged: bool = False

    @property
    def ref(self) -> str:
        return f"{self.book_id}#{self.page}"


@dataclass
class Answer:
    status: Status
    reason: str | None = None
    resumen: str = ""
    puntos: list[dict[str, Any]] = field(default_factory=list)
    relacion_con_escenarios: str = ""
    advertencias: list[str] = field(default_factory=list)
    dropped: int = 0
    passages_sent: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reason": self.reason, "resumen": self.resumen,
                "puntos": self.puntos, "relacion_con_escenarios": self.relacion_con_escenarios,
                "advertencias": self.advertencias, "dropped": self.dropped,
                "passages_sent": self.passages_sent, "label": LABEL}


Searcher = Callable[[str], list[Passage]]
Llm = Callable[[dict[str, Any]], "dict[str, Any] | None"]
_CTRL = re.compile("[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮]")
_REF = re.compile(r"^([a-z][a-z0-9_]*)\s*(?:[#:]|\s)\s*(?:p\.?\s*)?(\d+)$")


def _clean(text: str, limit: int) -> str:
    return " ".join(_CTRL.sub("", text).split())[:limit]


def build_context(question: str, passages: list[Passage], cards: list[KnowledgeCard],
                  scenario: str | None, state: str) -> dict[str, Any]:
    """Datos para el LLM: todo es dato no confiable; ningún libro entero, solo fragmentos."""
    return {
        "pregunta": _clean(question, MAX_QUESTION_CHARS),
        "escenario": scenario if scenario in SCENARIOS else None,
        "estado_actual": _clean(state, MAX_STATE_CHARS),
        "fichas": [{"id": c.id, "titulo": c.title, "parafrasis": c.claim,
                    "autor_evidencia": c.author_evidence,
                    "citas": [{"libro": x.book_id, "paginas": x.pages} for x in c.citations]}
                   for c in cards[:MAX_CARDS]],
        "pasajes": [{"fuente": p.ref, "fragmento": _clean(p.text, MAX_SNIPPET_CHARS)}
                    for p in passages[:MAX_PASSAGES]],
    }


def _valid_source(src: str, card_ids: set[str], refs: set[tuple[str, int]]) -> str | None:
    src = src.strip()
    if src in card_ids:
        return src
    m = _REF.match(src.lower())
    if m and (m.group(1), int(m.group(2))) in refs:
        return f"{m.group(1)}#{m.group(2)}"
    return None


def ask(question: str, *, search: Searcher, cards: list[KnowledgeCard], llm: Llm | None,
        scenario: str | None = None, state: str = "") -> Answer:
    """Pregunta a la biblioteca. Degrada a `no_data` con motivo claro (sin LLM, sin libros,
    sin pasajes ni fichas relacionadas, o salida inválida)."""
    question = question.strip()
    if not question:
        return Answer("no_data", "pregunta vacía")
    if llm is None:
        return Answer("no_data", "consulta apagada o sin clave (EIM_LIBRARY_LLM=1 y "
                                 "ANTHROPIC_API_KEY)")
    found = search(question)
    warnings: list[str] = []
    flagged = [p for p in found if p.flagged]
    if flagged:
        warnings.append(f"{len(flagged)} pasaje(s) excluido(s): texto dirigido a un modelo "
                        "(se trata como dato y no se envía)")
    passages = [p for p in found if not p.flagged and p.text.strip()][:MAX_PASSAGES]
    if not passages and not cards:
        return Answer("no_data", "sin libros indexados ni fichas relacionadas con la pregunta",
                      advertencias=warnings)
    ctx = build_context(question, passages, cards, scenario, state)
    try:
        raw = llm(ctx)
        if raw is None:
            return Answer("no_data", "el LLM no respondió (sin clave, sin red o límite de costo)",
                          advertencias=warnings, passages_sent=len(passages))
        out = AskOutput.model_validate(raw)
    except (ValidationError, ValueError, OSError, RuntimeError) as e:
        return Answer("no_data", f"salida del LLM inválida: {type(e).__name__}",
                      advertencias=warnings, passages_sent=len(passages))

    card_ids = {c.id for c in cards[:MAX_CARDS]}
    refs = {(p.book_id, p.page) for p in passages}
    points, dropped = [], 0
    for pt in out.puntos:
        src = _valid_source(pt.fuente, card_ids, refs)
        if src is None:
            dropped += 1
            continue
        points.append({"texto": pt.texto, "fuente": src,
                       "tipo": "ficha" if src in card_ids else "pasaje"})
    if dropped:
        warnings.append(f"{dropped} punto(s) descartado(s) por no citar una fuente entregada")
    if not points:
        warnings.append("ningún punto con fuente válida: respuesta no verificable")
        return Answer("degraded", "sin puntos con fuente válida",
                      advertencias=[*warnings, *out.advertencias], dropped=dropped,
                      passages_sent=len(passages))
    return Answer("ok", None, out.resumen, points, out.relacion_con_escenarios,
                  [*warnings, *[a for a in out.advertencias if a]], dropped, len(passages))


def related_cards(cards: list[KnowledgeCard], passages: list[Passage],
                  question: str) -> list[KnowledgeCard]:
    """Fichas útiles: las que citan páginas de los pasajes hallados o comparten palabras con la
    pregunta (sin estado `descartada`)."""
    pages = {(p.book_id, p.page) for p in passages}
    q = set(tokenize(question))
    scored = []
    for c in cards:
        if c.status == "descartada":
            continue
        hit = sum(1 for x in c.citations for pg in x.pages if (x.book_id, pg) in pages)
        overlap = len(q & set(tokenize(f"{c.title} {c.claim}")))
        if hit or overlap >= 2:
            scored.append((-(hit * 3 + overlap), c.id, c))
    return [c for _, _, c in sorted(scored)[:MAX_CARDS]]
