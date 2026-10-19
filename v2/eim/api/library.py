"""Rutas de la biblioteca: `GET /v2/library/cards/{id}` (T53), `GET /v2/library/catalog` y
`POST /v2/library/ask` (T55).

El agente `literature` emite solo `card_id`; el título, la paráfrasis y la cita se resuelven aquí
desde el cargador de T52 (`eim/data/library.py`). No expone texto de los libros. La consulta
(`ask`) solo informa; está apagada salvo `EIM_LIBRARY_LLM=1` + `ANTHROPIC_API_KEY`.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from eim.data.library import LibraryPaths, Registry, load_cards, load_catalog, search
from eim.data.providers.claude_library import ClaudeLibraryLlm, enabled
from eim.library import qa
from eim.library.schema import KnowledgeCard

CONFIRM = "library-ask"


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, KnowledgeCard], dict[str, dict]]:
    cards = {c.id: c for c in load_cards()}
    books = {b.id: {"title": b.title, "author": b.author, "year": b.year}
             for b in Registry.load().books.values()}
    return cards, books


def card_view(card: KnowledgeCard, books: dict[str, dict]) -> dict:
    return {
        "id": card.id, "title": card.title, "kind": card.kind, "claim": card.claim,
        "status": card.status, "verification": card.verification,
        "expected_effect": card.expected_effect.model_dump() if card.expected_effect else None,
        "applicability": card.applicability.model_dump(),
        "citations": [{**books.get(ct.book_id, {"title": ct.book_id, "author": "", "year": None}),
                       "book_id": ct.book_id, "chapter": ct.chapter, "pages": ct.pages,
                       "printed": ct.printed} for ct in card.citations],
        "label": "Hipótesis de un libro, no evidencia ni señal validada",
    }


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=qa.MAX_QUESTION_CHARS)
    scenario: str | None = Field(default=None, pattern="^(bull|neutral|bear)$")
    state: str = Field(default="", max_length=qa.MAX_STATE_CHARS)   # resumen del estado (dato)


def _catalog(cards: dict[str, KnowledgeCard], books: dict[str, dict], paths: LibraryPaths) -> dict:
    local = load_catalog(paths)
    by_status: dict[str, dict[str, int]] = {}
    for c in cards.values():
        for b in c.book_ids or {"_cruces"}:
            d = by_status.setdefault(b, {})
            d[c.status] = d.get(c.status, 0) + 1
    out = []
    for bid, meta in books.items():
        e = local.get(bid)
        out.append({"id": bid, **meta, "pages": e.pages if e else None,
                    "pages_with_text": e.pages_with_text if e else 0,
                    "index_status": e.status if e else "sin_ingerir",
                    "cards_by_status": by_status.get(bid, {})})
    return {"books": out, "cards_total": len(cards),
            "cards_by_status": {s: sum(1 for c in cards.values() if c.status == s)
                                for s in sorted({c.status for c in cards.values()})},
            "llm_enabled": enabled(), "label": qa.LABEL}


def build_library_router(loader: Callable[[], tuple[dict, dict]] = _load,
                         paths: Callable[[], LibraryPaths] = LibraryPaths.from_env,
                         llm: Callable[[], qa.Llm | None] | None = None) -> APIRouter:
    router = APIRouter()
    make_llm = llm or (lambda: ClaudeLibraryLlm() if enabled() else None)

    @router.get("/v2/library/catalog")
    def get_catalog() -> dict:
        cards, books = loader()
        return _catalog(cards, books, paths())

    @router.post("/v2/library/ask")
    def post_ask(body: AskBody, x_eim_confirm: str | None = Header(None)) -> dict:
        if x_eim_confirm != CONFIRM:
            raise HTTPException(403, f"falta la cabecera X-EIM-Confirm: {CONFIRM}")
        cards, books = loader()
        lp = paths()

        def find(q: str) -> list[qa.Passage]:
            return [qa.Passage(h.book_id, h.page, h.snippet, h.flagged)
                    for h in search(lp, q, k=qa.MAX_PASSAGES * 2)]

        related = _related_cards(cards, [p for p in find(body.question)], body.question)
        ans = qa.ask(body.question, search=find, cards=related, llm=make_llm(),
                     scenario=body.scenario, state=body.state)
        d = ans.as_dict()
        d["sources"] = {c.id: card_view(c, books) for c in related if c.id in
                        {p["fuente"] for p in d["puntos"]}}
        return d

    @router.get("/v2/library/cards/{card_id}")
    def get_card(card_id: str) -> dict:
        cards, books = loader()
        if card_id not in cards:
            raise HTTPException(404, f"ficha inexistente: {card_id}")
        return card_view(cards[card_id], books)

    return router


def _related_cards(cards: dict[str, KnowledgeCard], passages: list[qa.Passage],
                   question: str) -> list[KnowledgeCard]:
    """Fichas útiles: las que citan páginas de los pasajes hallados o comparten palabras con la
    pregunta (sin estado `descartada`)."""
    from eim.library.bm25 import tokenize
    pages = {(p.book_id, p.page) for p in passages}
    q = set(tokenize(question))
    scored = []
    for c in cards.values():
        if c.status == "descartada":
            continue
        hit = sum(1 for x in c.citations for pg in x.pages if (x.book_id, pg) in pages)
        overlap = len(q & set(tokenize(f"{c.title} {c.claim}")))
        if hit or overlap >= 2:
            scored.append((-(hit * 3 + overlap), c.id, c))
    return [c for _, _, c in sorted(scored)[:qa.MAX_CARDS]]
