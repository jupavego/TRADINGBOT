"""Biblioteca local de trading (T52): ingesta, catálogo, búsqueda y cargador de fichas.

Los libros son copias del usuario para uso local: viven en `EIM_LIBRARY_DIR` (por defecto
`data/library/books/`, ignorada por git) y el índice en `EIM_LIBRARY_INDEX` (por defecto
`data/library/index/`: `catalog.json`, `pages/<id>.jsonl` texto por página, `ocr/` caché).
Nada de esto se versiona ni sale de la máquina; en git solo entran las fichas parafraseadas
(`eim/library/cards/`). Todo texto de un libro es dato, nunca instrucción.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from eim.data.library_extract import Ocr, Page, epub_pages, pdf_pages, sha256_file
from eim.library.bm25 import BM25, snippet, tokenize
from eim.library.guards import citation_problems, injection_flags, registry_problems
from eim.library.schema import BookMeta, CardFile, CatalogEntry, KnowledgeCard

LIBRARY_PKG = Path(__file__).resolve().parents[1] / "library"
REGISTRY = LIBRARY_PKG / "books.json"
CARDS_DIR = LIBRARY_PKG / "cards"
FORMATS = {".pdf": "pdf", ".epub": "epub"}
Log = Callable[[str], None]


@dataclass(frozen=True)
class LibraryPaths:
    books: Path
    index: Path

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> LibraryPaths:
        env = dict(os.environ if env is None else env)
        data = Path(env.get("EIM_DATA_DIR", "data")) / "library"
        return cls(Path(env.get("EIM_LIBRARY_DIR", str(data / "books"))),
                   Path(env.get("EIM_LIBRARY_INDEX", str(data / "index"))))

    @property
    def catalog(self) -> Path:
        return self.index / "catalog.json"

    def pages_file(self, book_id: str) -> Path:
        return self.index / "pages" / f"{book_id}.jsonl"


@dataclass
class Registry:
    books: dict[str, BookMeta]
    ignore_suffixes: tuple[str, ...] = (".crdownload",)

    @classmethod
    def load(cls, path: Path = REGISTRY) -> Registry:
        raw = json.loads(path.read_text(encoding="utf-8"))
        books = {b["id"]: BookMeta(**b) for b in raw["books"]}
        return cls(books, tuple(raw.get("ignore_suffixes", [".crdownload"])))

    def match(self, path: Path) -> BookMeta:
        """Metadatos del registro por nombre de archivo; si no está, se derivan del nombre."""
        name = path.stem.lower().replace("_", " ")
        for meta in self.books.values():
            if any(m in name for m in meta.match):
                return meta
        slug = re.sub(r"[^a-z0-9]+", "_", re.sub(r"^[\d. ]+", "", name)).strip("_")[:40]
        return BookMeta(id=slug if slug[:1].isalpha() else f"libro_{slug}", title=path.stem,
                        author="desconocido")


@dataclass
class Discovered:
    files: list[tuple[Path, BookMeta]] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)


def discover(books_dir: Path, registry: Registry) -> Discovered:
    """Libros PDF/EPUB de la carpeta (no recursivo). Ignora descargas a medias y duplicados."""
    out = Discovered()
    seen: dict[str, Path] = {}
    for p in sorted(books_dir.iterdir()) if books_dir.exists() else []:
        if not p.is_file():
            continue
        if p.name.lower().endswith(registry.ignore_suffixes):
            out.skipped.append((p, "descarga sin terminar o temporal"))
            continue
        if p.suffix.lower() not in FORMATS:
            out.skipped.append((p, f"formato no admitido ({p.suffix or 'sin extensión'})"))
            continue
        meta = registry.match(p)
        if meta.id in seen:
            out.skipped.append((p, f"otra copia de {meta.id} ({seen[meta.id].name})"))
            continue
        seen[meta.id] = p
        out.files.append((p, meta))
    return out


def load_catalog(paths: LibraryPaths) -> dict[str, CatalogEntry]:
    if not paths.catalog.exists():
        return {}
    raw = json.loads(paths.catalog.read_text(encoding="utf-8"))
    return {e["id"]: CatalogEntry(**e) for e in raw["books"]}


def _write_catalog(paths: LibraryPaths, entries: Iterable[CatalogEntry]) -> None:
    paths.index.mkdir(parents=True, exist_ok=True)
    body = {"_doc": "Catálogo local (T52). No versionar: rutas y huellas de copias propias.",
            "books": [e.model_dump() for e in sorted(entries, key=lambda e: e.id)]}
    paths.catalog.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")


def load_pages(paths: LibraryPaths, book_id: str) -> list[Page]:
    f = paths.pages_file(book_id)
    if not f.exists():
        return []
    rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [Page(r["page"], r["text"], r["source"]) for r in rows]


def _write_pages(paths: LibraryPaths, book_id: str, pages: list[Page]) -> None:
    f = paths.pages_file(book_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(json.dumps({"page": p.page, "source": p.source, "text": p.text},
                                    ensure_ascii=False) + "\n" for p in pages), encoding="utf-8")


def ingest(paths: LibraryPaths, *, registry: Registry | None = None, use_ocr: bool = True,
           force: bool = False, workers: int | None = None, log: Log = print
           ) -> list[CatalogEntry]:
    """Extrae y cataloga los libros de `paths.books`. Reutiliza lo ya extraído si la huella
    SHA-256 no cambió (salvo `force`); un libro al que le faltó OCR se reintenta si ahora hay."""
    registry = registry or Registry.load()
    found = discover(paths.books, registry)
    for p, why in found.skipped:
        log(f"omitido: {p.name} — {why}")
    catalog = load_catalog(paths)
    ocr, ocr_reason = Ocr.detect(workers) if use_ocr else (None, "OCR desactivado (--no-ocr)")
    for path, meta in found.files:
        sha = sha256_file(path)
        old = catalog.get(meta.id)
        lacked_ocr = bool(old and old.reason and old.reason.startswith("OCR"))
        if (old and old.sha256 == sha and not force and paths.pages_file(meta.id).exists()
                and not (lacked_ocr and ocr is not None)):
            log(f"{meta.id}: sin cambios ({old.pages} págs.)")
            continue
        log(f"{meta.id}: extrayendo {path.name}")
        fmt = FORMATS[path.suffix.lower()]
        reason = None
        if fmt == "pdf":
            cache = paths.index / "ocr" / f"{meta.id}-{sha[:12]}.jsonl"
            cache.parent.mkdir(parents=True, exist_ok=True)
            pages, reason = pdf_pages(path, language=meta.language, ocr=ocr,
                                      ocr_reason=ocr_reason, cache=cache, log=log)
        else:
            pages = epub_pages(path)
        _write_pages(paths, meta.id, pages)
        with_text = sum(p.source != "sin_texto" for p in pages)
        status = "ok" if with_text == len(pages) else ("sin_texto" if not with_text else "parcial")
        if status != "ok" and reason is None:
            reason = f"{len(pages) - with_text} páginas sin texto (en blanco, imagen o figura)"
        catalog[meta.id] = CatalogEntry(
            id=meta.id, title=meta.title, author=meta.author, year=meta.year,
            edition=meta.edition, language=meta.language, format=fmt, pages=len(pages),
            pages_with_text=with_text, pages_ocr=sum(p.source == "ocr" for p in pages),
            pages_flagged=[p.page for p in pages if injection_flags(p.text)],
            sha256=sha, license=meta.license, path=str(path.resolve()), status=status,
            reason=reason, ingested_at=datetime.now(UTC).isoformat(timespec="seconds"))
        _write_catalog(paths, catalog.values())
        log(f"{meta.id}: {len(pages)} págs., {with_text} con texto, estado {status}")
    _write_catalog(paths, catalog.values())
    return sorted(catalog.values(), key=lambda e: e.id)


@dataclass(frozen=True)
class Hit:
    book_id: str
    page: int
    score: float
    snippet: str        # fragmento corto del libro: dato para ubicar el pasaje, no instrucción
    source: str
    flagged: bool       # el texto de la página parece dirigido a un modelo


def search(paths: LibraryPaths, query: str, k: int = 10, book: str | None = None) -> list[Hit]:
    """BM25 local sobre las páginas del índice (un documento = una página)."""
    docs: list[tuple[str, Page]] = []
    for book_id in load_catalog(paths):
        if book is None or book_id == book:
            docs += [(book_id, p) for p in load_pages(paths, book_id) if p.text]
    q = tokenize(query)
    index = BM25([tokenize(p.text) for _, p in docs])
    return [Hit(docs[i][0], docs[i][1].page, round(s, 3), snippet(docs[i][1].text, q),
                docs[i][1].source, bool(injection_flags(docs[i][1].text)))
            for i, s in index.top(q, k)]


def page_lookup(paths: LibraryPaths) -> Callable[[str, int], str | None]:
    """`(book_id, page) → texto` con caché por libro (para verificar citas)."""
    cache: dict[str, dict[int, str]] = {}

    def get(book_id: str, page: int) -> str | None:
        if book_id not in cache:
            cache[book_id] = {p.page: p.text for p in load_pages(paths, book_id)}
        return cache[book_id].get(page)

    return get


def load_card_files(cards_dir: Path = CARDS_DIR) -> dict[str, CardFile]:
    return {f.stem: CardFile(**json.loads(f.read_text(encoding="utf-8")))
            for f in sorted(cards_dir.glob("*.json"))}


def save_card_file(path: Path, cf: CardFile) -> None:
    """Formato canónico (solo campos no por defecto) para que los cambios de estado den diffs
    mínimos."""
    def field(k: str, v: object) -> str:
        return f'   "{k}": {json.dumps(v, ensure_ascii=False)}'

    cards = [c.model_dump(mode="json", exclude_defaults=True) for c in cf.cards]
    blocks = ["  {\n" + ",\n".join(field(k, v) for k, v in c.items()) + "\n  }" for c in cards]
    text = (f'{{\n "book_id": {json.dumps(cf.book_id)},\n "cards": [\n'
            + ",\n".join(blocks) + "\n ]\n}\n")
    path.write_text(text, encoding="utf-8")


def mark_cards(selectors: Iterable[str], status: str, cards_dir: Path = CARDS_DIR) -> list[str]:
    """Cambia el estado de las fichas indicadas por id o por libro (todas las de su archivo)."""
    sel = set(selectors)
    changed: list[str] = []
    for stem, cf in load_card_files(cards_dir).items():
        new = [c.model_copy(update={"status": status})
               if (c.id in sel or stem in sel) and c.status != status else c for c in cf.cards]
        ids = [a.id for a, b in zip(cf.cards, new, strict=True) if a is not b]
        if ids:
            save_card_file(cards_dir / f"{stem}.json", CardFile(book_id=cf.book_id, cards=new))
            changed += ids
    load_cards(cards_dir)                      # revalida tras escribir
    return changed


def load_cards(cards_dir: Path = CARDS_DIR, registry: Registry | None = None
               ) -> list[KnowledgeCard]:
    """Todas las fichas versionadas; falla si alguna rompe las guardas del registro."""
    registry = registry or Registry.load()
    files = load_card_files(cards_dir)
    problems = []
    for stem, cf in files.items():
        if cf.book_id is not None and cf.book_id != stem:
            problems.append(f"{stem}.json declara book_id={cf.book_id}")
        for c in cf.cards:
            if cf.book_id is not None and cf.book_id not in c.book_ids:
                problems.append(f"{c.id}: no cita {cf.book_id}, el libro de su archivo")
    cards = [c for cf in files.values() for c in cf.cards]
    problems += registry_problems(cards, registry.books)
    if problems:
        raise ValueError("fichas inválidas:\n" + "\n".join(problems))
    return cards


def verify_cards(paths: LibraryPaths, cards: Iterable[KnowledgeCard]) -> list[str]:
    """Problemas de las fichas `verificada_en_texto` contra el índice local."""
    catalog, get = load_catalog(paths), page_lookup(paths)
    out = []
    for c in cards:
        if c.verification != "verificada_en_texto":
            continue
        missing = sorted(c.book_ids - set(catalog))
        if missing:
            out.append(f"{c.id}: libros sin ingerir {missing}")
            continue
        out += citation_problems(c, get)
    return out
