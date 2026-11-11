"""Catálogo digital consultable (T151), puro: buscar, filtrar, relacionar con estrategias y contar.

Independiente del catálogo local (T52) pero integrado con él: el resumen (`overview`) suma las dos
bibliotecas y la búsqueda devuelve obras digitales; la consulta LLM (T55) sigue sobre la local.
"""

from __future__ import annotations

import re
from collections import Counter

from eim.library.bm25 import BM25, fold, tokenize
from eim.library.digital.schema import CATEGORY_NAMES, DigitalCard, DigitalRef
from eim.library.digital.taxonomy import CONCEPTS, STRATEGY_MAP

STRATEGIES = ("ind_supertrend", "ind_cruce_ema", "ind_macd", "ind_adx", "ind_donchian",
              "ind_bb_ruptura", "ind_rsi", "ind_bb_reversion", "base_tendencia", "base_retroceso",
              "escenario_dominante", "escenario_rango", "escenario_retroceso", "consenso_fuerte",
              "consenso_sintesis", "contra_sintesis", "ppp_tendencia", "sugerencia_alineada",
              "control_aleatorio")


def _doc(r: DigitalRef) -> str:
    v, c = r.verified, r.curated
    names = " ".join(CONCEPTS[x].name for x in c.concepts if x in CONCEPTS)
    return " ".join(filter(None, [v.title if v else "", " ".join(v.authors) if v else "",
                                  c.description, " ".join(c.methods), names, " ".join(c.concepts),
                                  v.venue if v else ""]))


def related_strategies(r: DigitalRef) -> list[str]:
    """Estrategias del bróker cuyos conceptos coinciden con los de la obra."""
    own = set(r.curated.concepts)
    out = []
    for s in STRATEGIES:
        for pat, cs in STRATEGY_MAP:
            if re.search(pat, s) and own & set(cs):
                out.append(s)
                break
    return out


def view(r: DigitalRef, card: DigitalCard | None = None) -> dict:
    v, c = r.verified, r.curated
    return {
        "id": r.id, "title": v.title if v else r.locator.expect,
        "authors": v.authors if v else [], "year": v.year if v else None,
        "venue": v.venue if v else None, "publisher": v.publisher if v else None,
        "doc_type": v.doc_type if v else None,
        "category": c.category, "category_name": CATEGORY_NAMES[c.category],
        "description": c.description, "concepts": c.concepts,
        "concept_names": [CONCEPTS[x].name for x in c.concepts if x in CONCEPTS],
        "methods": c.methods, "application": c.application, "markets": c.markets,
        "url": v.url if v else (r.locator.url or None), "oa_url": v.oa_url if v else None,
        "source": v.source if v else None, "access": v.access if v else "desconocido",
        "availability": v.availability if v else "pendiente",
        "verified_at": v.verified_at if v else None, "reliability": r.reliability,
        "problem": r.problem, "curated_by": "curado (no viene del registro)",
        "stances": [s.model_dump() for s in c.stances],
        "related_strategies": related_strategies(r),
        "card": card.model_dump() if card else None,
        "read": card.coverage if card else "metadatos",
    }


def search(refs: list[DigitalRef], q: str = "", author: str = "", title: str = "",
           category: str = "", availability: str = "", concept: str = "",
           strategy: str = "", k: int = 200) -> list[DigitalRef]:
    """Filtra por autor, título, categoría, disponibilidad, concepto o estrategia; ordena por q."""
    out = list(refs)
    if author:
        a = fold(author)
        out = [r for r in out if r.verified and any(a in fold(x) for x in r.verified.authors)]
    if title:
        t = fold(title)
        out = [r for r in out if t in fold(r.verified.title if r.verified else r.locator.expect)]
    if category:
        out = [r for r in out if r.curated.category == category.upper()]
    if availability:
        out = [r for r in out if (r.verified.availability if r.verified else "pendiente")
               == availability or (r.verified and r.verified.access == availability)]
    if concept:
        out = [r for r in out if concept in r.curated.concepts]
    if strategy:
        out = [r for r in out if strategy.split("@")[0] in related_strategies(r)]
    if q.strip() and out:
        idx = BM25([tokenize(_doc(r)) for r in out])
        ranked = idx.top(tokenize(q), k)
        out = [out[i] for i, _ in ranked]
    return out[:k]


def overview(refs: list[DigitalRef], cards: dict[str, DigitalCard], local_books: int,
             local_cards: int) -> dict:
    """Recuentos para el panel (T158)."""
    ok = [r for r in refs if r.ok]
    avail = Counter(r.verified.availability if r.verified else "pendiente" for r in refs)
    access = Counter(r.verified.access if r.verified else "desconocido" for r in refs)
    methods = Counter(m for r in ok for m in r.curated.methods)
    read = Counter(c.coverage for c in cards.values())
    return {
        "digital_total": len(refs), "digital_verified": len(ok),
        "pending_verification": len(refs) - len(ok),
        "full_text": avail.get("texto_completo", 0),
        "partial": avail.get("solo_resumen", 0) + avail.get("solo_metadatos", 0),
        "by_availability": dict(avail), "by_access": dict(access),
        "by_category": {k: {"name": n, "n": sum(r.curated.category == k for r in refs)}
                        for k, n in CATEGORY_NAMES.items()},
        "cards": len(cards), "read": dict(read),
        "stances": sum(len(r.curated.stances) for r in ok),
        "stances_verified": sum(len(c.stances_verified) for c in cards.values()),
        "methods_identified": len(methods), "top_methods": methods.most_common(8),
        "local_books": local_books, "local_cards": local_cards,
        "total_references": len(refs) + local_books,
    }
