"""Investigación de la biblioteca digital (T152): descargar lo legal, leer y extraer fichas.

Para cada obra verificada: usa el texto completo si ya se descargó (o lo descarga con `full=True`,
solo de obras con acceso legal), si no el resumen del registro (OpenAlex o arXiv). Sin conexión
trabaja con la caché. Cada pasada queda anotada en `research.jsonl` (lo que se leyó de cada obra),
que es lo que el panel muestra como «últimas investigaciones».
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from io import BytesIO

import httpx

from eim.data.library_digital import (
    DigitalPaths,
    Http,
    _arxiv,
    _cached,
    abstract,
    local_text,
    log_research,
)
from eim.library.digital.extract import extract
from eim.library.digital.registry import parse_arxiv
from eim.library.digital.schema import DigitalCard, DigitalRef

Log = Callable[[str], None]


def fetch_text(ref: DigitalRef, paths: DigitalPaths, http: Http, max_pages: int = 60) -> str:
    """Descarga y extrae el texto completo de una obra con acceso legal (PDF u HTML).

    Solo obras con `oa_url` y acceso abierto o gratuito; nunca de pago. Devuelve "" si no pudo.
    """
    v = ref.verified
    if v is None or not v.oa_url or v.access not in ("abierto", "gratuito"):
        return ""
    try:
        r = http.get(v.oa_url)
        r.raise_for_status()
    except httpx.HTTPError:
        return ""
    if "pdf" in r.headers.get("content-type", "") or r.content[:4] == b"%PDF":
        text = _pdf_text(r.content, max_pages)
    else:
        text = _strip_html(r.text)
    if len(text) < 2000:      # páginas de aterrizaje o muros de pago: no es el texto completo
        return ""
    out = paths.text(ref.id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text


def _pdf_text(data: bytes, max_pages: int) -> str:
    try:
        from pypdf import PdfReader  # extra `library` (T52); sin él, solo resúmenes
    except ImportError:
        return ""
    try:
        pages = PdfReader(BytesIO(data)).pages[:max_pages]
        return "\n".join((p.extract_text() or "") for p in pages)
    except Exception:  # noqa: BLE001 — un PDF roto no tumba la investigación
        return ""


def _strip_html(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def read(ref: DigitalRef, paths: DigitalPaths, http: Http | None, full: bool) -> tuple[str, str]:
    """(texto, cobertura) de lo mejor que se puede leer legalmente de una obra."""
    text = local_text(ref.id, paths)
    if not text and full and http is not None:
        text = fetch_text(ref, paths, http)
    if text:
        return text, "texto_completo"
    abs_ = abstract(ref, paths)
    if not abs_ and ref.locator.arxiv and http is not None:
        body, _ = _cached(paths, "arxiv", ref.locator.arxiv,
                          lambda: _arxiv(http, ref.locator.arxiv or ""), False)
        abs_ = (parse_arxiv(body) or {}).get("summary", "") if body else ""
    return (abs_, "resumen") if abs_ else ("", "metadatos")


def research(refs: list[DigitalRef], paths: DigitalPaths, http: Http | None = None,
             full: bool = False, only: set[str] | None = None,
             log: Log = print) -> dict[str, DigitalCard]:
    """Fichas de todas las obras verificadas (o de `only`)."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    cards: dict[str, DigitalCard] = {}
    for r in refs:
        if not r.ok or (only and r.id not in only):
            continue
        text, cov = read(r, paths, http, full)
        card = extract(r, text, cov, now)  # type: ignore[arg-type]
        cards[r.id] = card
        log(f"{r.id}: {cov}, {len(card.concepts)} conceptos, posturas verificadas "
            f"{len(card.stances_verified)}/{len(r.curated.stances)}")
    log_research(paths, {"kind": "research", "full": full, "n": len(cards),
                         "coverage": _count(c.coverage for c in cards.values()),
                         "stances_verified": sum(len(c.stances_verified) for c in cards.values()),
                         "refs": sorted(cards)[:200]})
    return cards


def _count(xs) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out


def dump(cards: dict[str, DigitalCard]) -> str:
    return json.dumps({k: v.model_dump() for k, v in cards.items()}, ensure_ascii=False)
