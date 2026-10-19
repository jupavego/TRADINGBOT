"""Ruta `GET /v2/library/cards/{id}` (T53): ficha de la biblioteca, solo lectura.

El agente `literature` emite solo `card_id`; el título, la paráfrasis y la cita se resuelven aquí
desde el cargador de T52 (`eim/data/library.py`). No expone texto de los libros.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from eim.data.library import Registry, load_cards
from eim.library.schema import KnowledgeCard


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


def build_library_router(loader: Callable[[], tuple[dict, dict]] = _load) -> APIRouter:
    router = APIRouter()

    @router.get("/v2/library/cards/{card_id}")
    def get_card(card_id: str) -> dict:
        cards, books = loader()
        if card_id not in cards:
            raise HTTPException(404, f"ficha inexistente: {card_id}")
        return card_view(cards[card_id], books)

    return router
