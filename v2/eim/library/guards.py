"""Guardas de la biblioteca (T52), puras.

1. **El texto de los libros es dato, nunca instrucción.** Un PDF puede traer texto dirigido a un
   modelo («ignora las instrucciones…»). Aquí solo se detecta y se marca (`injection_flags`); el
   texto nunca se ejecuta ni se interpreta, y quien lo pase a un LLM (T55) debe entregarlo como
   bloque de datos citado, igual que los titulares de T24.
2. **Derechos de autor**: `claim` ≤ 400 caracteres, `quote` ≤ 25 palabras (en el esquema) y toda
   ficha `verificada_en_texto` cita al menos un libro del registro con páginas existentes.
3. **Citas comprobables** contra el índice local: los `terms` de cada cita y la `quote`
   aparecen en las páginas citadas (`citation_problems`).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from eim.library.bm25 import fold, words
from eim.library.schema import MAX_CLAIM_CHARS, MAX_QUOTE_WORDS, BookMeta, KnowledgeCard

_INJECTION = [re.compile(p) for p in (
    r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|all|earlier)\b.{0,20}"
    r"\b(instructions?|prompts?|rules)\b",
    r"\b(ignora|olvida|descarta)\b.{0,40}\b(instrucciones|indicaciones|reglas)\b",
    r"\bsystem prompt\b",
    r"\byou are (now )?(an? )?(ai|assistant|language model|chatgpt|claude)\b",
    r"\b(eres|ahora eres) (un |una )?(asistente|modelo de lenguaje|ia)\b",
    r"<\|?(im_start|im_end|system)\|?>",
    r"^\s*(system|assistant|human)\s*:\s*(you|eres|tu|ignore|ignora|from now|a partir)\b",
)]


def injection_flags(text: str) -> list[str]:
    """Patrones de texto dirigido a un modelo encontrados en `text` (vacío = nada sospechoso)."""
    low = fold(text)
    found = []
    for rx in _INJECTION:
        if rx.search(low) or any(rx.search(line) for line in low.splitlines()):
            found.append(rx.pattern[:40])
    return found


def copyright_problems(card: KnowledgeCard) -> list[str]:
    """Límites de extensión (redundantes con el esquema, por si se construye sin validar)."""
    out = []
    if len(card.claim) > MAX_CLAIM_CHARS:
        out.append(f"{card.id}: claim > {MAX_CLAIM_CHARS} caracteres")
    if card.quote and len(card.quote.split()) > MAX_QUOTE_WORDS:
        out.append(f"{card.id}: quote > {MAX_QUOTE_WORDS} palabras")
    return out


def registry_problems(cards: Iterable[KnowledgeCard], books: dict[str, BookMeta]) -> list[str]:
    """Ids únicos, libros del registro, páginas dentro del libro y relacionadas existentes."""
    cards = list(cards)
    out: list[str] = []
    ids = [c.id for c in cards]
    out += [f"{i}: id repetido" for i in sorted({i for i in ids if ids.count(i) > 1})]
    known = set(ids)
    for c in cards:
        out += copyright_problems(c)
        if c.verification == "verificada_en_texto" and not any(x.pages for x in c.citations):
            out.append(f"{c.id}: verificada sin página")
        for x in c.citations:
            meta = books.get(x.book_id)
            if meta is None:
                out.append(f"{c.id}: libro desconocido {x.book_id}")
            elif meta.pages and max(x.pages) > meta.pages:
                out.append(f"{c.id}: página {max(x.pages)} > {meta.pages} en {x.book_id}")
        out += [f"{c.id}: relacionada inexistente {r.id}" for r in c.related if r.id not in known]
    return out


def _contains(haystack: str, needle: str) -> bool:
    """¿`needle` aparece en `haystack` como secuencia de palabras normalizadas?

    Si no, se compara sin espacios: algunos PDF parten las palabras («m oney», «st ocks»).
    """
    n, h = words(needle), words(haystack)
    if not n:
        return False
    return " ".join(n) in " ".join(h) or "".join(n) in "".join(h)


def citation_problems(card: KnowledgeCard,
                      page_text: Callable[[str, int], str | None]) -> list[str]:
    """Comprueba la ficha contra el texto local: `page_text(book_id, page)` → texto o None."""
    out = []
    quote_found = card.quote is None
    for x in card.citations:
        texts = []
        for p in x.pages:
            t = page_text(x.book_id, p)
            if t is None:
                out.append(f"{card.id}: {x.book_id} p. {p} no está en el índice")
            else:
                texts.append(t)
        joined = "\n".join(texts)
        if texts:
            # el término puede partirse entre dos páginas consecutivas
            for term in x.terms:
                if not _contains(joined, term):
                    out.append(f"{card.id}: «{term}» no aparece en {x.book_id} p. {x.pages}")
            if card.quote and _contains(joined, card.quote):
                quote_found = True
    if not quote_found:
        out.append(f"{card.id}: la cita textual no aparece en las páginas citadas")
    return out
