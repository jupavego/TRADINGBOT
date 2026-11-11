"""Traducción pura de las respuestas de los registros (OpenAlex, arXiv, web) a `Verified` (T151).

Sin red: recibe el JSON/XML ya descargado. Decide acceso y disponibilidad con reglas fijas y
escritas aquí, para que nadie «ascienda» una obra de pago a texto completo:
- OpenAlex `oa_status` gold/diamond/hybrid/green → `abierto`; bronze → `gratuito`; closed →
  `suscripcion`. Texto completo solo si hay `oa_url`.
- arXiv → `abierto` y texto completo (el PDF de arXiv siempre es legal de leer).
- Web oficial que responde 200 → `gratuito` y texto completo (lo publica su autor o institución).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from eim.library.bm25 import words
from eim.library.digital.schema import Access, Availability, DocType, Verified

_OA = {"gold": "abierto", "diamond": "abierto", "hybrid": "abierto", "green": "abierto",
       "bronze": "gratuito", "closed": "suscripcion"}
_TYPES: dict[str, DocType] = {"article": "articulo", "review": "articulo", "letter": "articulo",
                              "preprint": "preprint", "book": "libro", "book-chapter": "capitulo",
                              "report": "informe", "dissertation": "otro",
                              "conference-paper": "articulo", "proceedings-article": "articulo"}
ATOM = "{http://www.w3.org/2005/Atom}"


def title_matches(expect: str, title: str) -> bool:
    """¿Contiene el título devuelto todas las palabras significativas del fragmento esperado?"""
    want = [w for w in words(expect) if len(w) > 2]
    have = set(words(title))
    return bool(want) and sum(w in have for w in want) / len(want) >= 0.8


def clean_title(title: str) -> str:
    """Quita notas al pie pegadas al título por el registro («sentiment1We are grateful…»)."""
    if len(title) > 120:
        m = re.search(r"(?<=[a-z])\d+(?=[A-Z])", title)
        if m:
            return title[:m.start()].strip()
    return title


def abstract_from_index(inv: dict[str, list[int]] | None) -> str:
    """Resumen de OpenAlex (índice invertido palabra → posiciones) como texto corrido."""
    if not inv:
        return ""
    slots: dict[int, str] = {}
    for word, positions in inv.items():
        for p in positions:
            slots[p] = word
    return " ".join(slots[i] for i in sorted(slots))


def from_openalex(w: dict, today: str) -> Verified:
    oa = w.get("open_access") or {}
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    best = w.get("best_oa_location") or {}
    oa_url = oa.get("oa_url") or best.get("pdf_url") or best.get("landing_page_url")
    access: Access = _OA.get(oa.get("oa_status") or "", "desconocido")  # type: ignore[assignment]
    if access == "suscripcion" and oa_url:
        access = "gratuito"
    has_abs = bool(w.get("abstract_inverted_index"))
    avail: Availability = ("texto_completo" if oa_url and access != "suscripcion"
                           else "solo_resumen" if has_abs else "solo_metadatos")
    doi = (w.get("doi") or "").replace("https://doi.org/", "")
    t = _TYPES.get(w.get("type") or "", "otro")
    if t == "articulo" and (src.get("type") == "repository" or "arxiv" in doi.lower()):
        t = "preprint"
    return Verified(
        title=clean_title(w.get("title") or w.get("display_name") or ""),
        authors=[a["author"]["display_name"] for a in w.get("authorships", [])
                 if a.get("author", {}).get("display_name")][:8],
        year=w.get("publication_year"), venue=src.get("display_name"),
        publisher=src.get("host_organization_name"), doc_type=t,
        url=f"https://doi.org/{doi}" if doi else (loc.get("landing_page_url") or w.get("id", "")),
        oa_url=oa_url if access != "suscripcion" else None, access=access, availability=avail,
        source="openalex", verified_at=today, cited_by=w.get("cited_by_count"),
        has_abstract=has_abs)


def parse_arxiv(xml: str) -> dict | None:
    """Primera entrada de la API de arXiv → {title, authors, year, summary, id}."""
    root = ET.fromstring(xml)
    e = root.find(f"{ATOM}entry")
    if e is None or e.find(f"{ATOM}title") is None:
        return None
    clean = lambda s: re.sub(r"\s+", " ", s or "").strip()  # noqa: E731
    return {"title": clean(e.findtext(f"{ATOM}title")),
            "authors": [clean(a.findtext(f"{ATOM}name")) for a in e.findall(f"{ATOM}author")],
            "year": int((e.findtext(f"{ATOM}published") or "0000")[:4]) or None,
            "summary": clean(e.findtext(f"{ATOM}summary")),
            "id": clean(e.findtext(f"{ATOM}id"))}


def from_arxiv(a: dict, arxiv_id: str, today: str) -> Verified:
    return Verified(title=a["title"], authors=a["authors"][:8], year=a["year"], venue="arXiv",
                    publisher="Cornell University", doc_type="preprint",
                    url=f"https://arxiv.org/abs/{arxiv_id}",
                    oa_url=f"https://arxiv.org/pdf/{arxiv_id}", access="abierto",
                    availability="texto_completo", source="arxiv", verified_at=today,
                    has_abstract=bool(a.get("summary")))


def html_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def from_web(url: str, title: str, meta: dict, today: str) -> Verified:
    """Obra en un sitio oficial (curso, informe, libro libre o ficha de editorial).

    `meta` viene curado. Por defecto la página se lee gratis y entera; una ficha de editorial
    de un libro de pago lo declara con `access: suscripcion` y `availability: solo_metadatos`.
    """
    access = meta.get("access", "gratuito")
    avail = meta.get("availability", "texto_completo")
    return Verified(title=meta.get("title") or title, authors=meta.get("authors", []),
                    year=meta.get("year"), venue=meta.get("venue"),
                    publisher=meta.get("publisher"), doc_type=meta.get("doc_type", "otro"),
                    url=url, oa_url=url if avail == "texto_completo" else None, access=access,
                    availability=avail, source="web", verified_at=today, has_abstract=False)
