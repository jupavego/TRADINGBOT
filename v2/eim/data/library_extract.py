"""Extracción de texto por página de los libros (T52): PDF (pypdf), EPUB (biblioteca estándar)
y OCR opcional con Tesseract (vía pytesseract) para PDF escaneados.

Dependencias opcionales `library` (pypdf BSD-3, pytesseract Apache-2.0, Pillow MIT-CMU; revisadas
con pip-audit). Sin pypdf no se ingieren PDF; sin Tesseract las páginas sin capa de texto quedan
`sin_texto` y el catálogo dice por qué. El texto extraído es dato (ver `eim/library/guards.py`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import zipfile
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from xml.etree import ElementTree

MIN_CHARS = 25                 # menos que esto en una página = sin capa de texto útil
EPUB_PAGE_CHARS = 2000         # tamaño de la «página» de un EPUB (fragmento)
EPUB_MAX_MEMBER = 20 * 2**20   # defensa ante zips desproporcionados
TESS_LANG = {"en": "eng", "es": "spa"}
WIN_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
Log = Callable[[str], None]


@dataclass(frozen=True)
class Page:
    page: int                  # 1 = primera página del archivo
    text: str
    source: Literal["texto", "ocr", "sin_texto"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(s: str) -> str:
    """Quita caracteres de control, une guiones de fin de línea y compacta espacios."""
    s = _CTRL.sub(" ", s.replace("\r\n", "\n").replace("\r", "\n"))
    s = re.sub(r"(\w)[-\u00ac\u00ad\u2010\u2011] *\n *(\w)", r"\1\2", s)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    s = re.sub(r" ?\n ?", "\n", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


class Ocr:
    """Tesseract local. `detect()` → instancia o (None, motivo)."""

    def __init__(self, cmd: str, langs: set[str], workers: int):
        self.cmd, self.langs, self.workers = cmd, langs, workers

    @classmethod
    def detect(cls, workers: int | None = None) -> tuple[Ocr | None, str | None]:
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError:
            return None, "OCR no disponible: falta pytesseract/Pillow (pip install -e .[library])"
        cmd = os.environ.get("EIM_TESSERACT") or shutil.which("tesseract")
        if not cmd and WIN_TESSERACT.exists():
            cmd = str(WIN_TESSERACT)
        if not cmd:
            return None, "OCR no disponible: Tesseract no está instalado (o EIM_TESSERACT)"
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = cmd
        try:
            langs = set(pytesseract.get_languages(config=""))
        except Exception as e:  # binario roto o inaccesible
            return None, f"OCR no disponible: Tesseract no responde ({type(e).__name__})"
        n = workers or max(1, (os.cpu_count() or 2) - 1)
        os.environ.setdefault("OMP_THREAD_LIMIT", "1")   # un hilo por proceso de Tesseract
        return cls(cmd, langs, n), None

    def lang_for(self, language: str) -> str | None:
        code = TESS_LANG.get(language, "eng")
        return code if code in self.langs else ("eng" if "eng" in self.langs else None)

    def read(self, image: Any, lang: str) -> str:
        import pytesseract
        return pytesseract.image_to_string(image, lang=lang)


def _load_cache(cache: Path | None) -> dict[int, str]:
    if cache is None or not cache.exists():
        return {}
    out = {}
    for line in cache.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[int(row["page"])] = row["text"]
    return out


def _page_image(page: Any) -> Any | None:
    """La imagen más grande de la página (un escaneo trae una por página)."""
    try:
        imgs = list(page.images)
    except Exception:
        return None
    if not imgs:
        return None
    best = max(imgs, key=lambda im: len(im.data))
    try:
        return best.image
    except Exception:
        return None


def pdf_pages(path: Path, *, language: str = "en", ocr: Ocr | None = None,
              ocr_reason: str | None = None, cache: Path | None = None,
              log: Log = print) -> tuple[list[Page], str | None]:
    """Texto por página. Páginas sin texto → OCR si hay motor; si no, `sin_texto` (+ motivo).

    El OCR es lento (~3 s/página): se paraleliza y se guarda página a página en `cache`
    (JSONL), así una ingesta interrumpida continúa donde quedó.
    """
    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(str(path))
    texts: dict[int, str] = {}
    blank: list[int] = []
    for i, p in enumerate(reader.pages, start=1):
        try:
            t = clean_text(p.extract_text() or "")
        except Exception:
            t = ""
        if len(t) >= MIN_CHARS:
            texts[i] = t
        else:
            blank.append(i)
    n = len(reader.pages)
    reason = None
    ocr_done: dict[int, str] = {}
    if blank and ocr is not None and (lang := ocr.lang_for(language)):
        ocr_done = _ocr_pages(reader, blank, ocr, lang, cache, log)
    elif blank:
        reason = ocr_reason or (f"OCR no disponible: falta el idioma {language} en Tesseract"
                                if ocr else "OCR no disponible")
    pages = []
    for i in range(1, n + 1):
        if i in texts:
            pages.append(Page(i, texts[i], "texto"))
        elif len(ocr_done.get(i, "")) >= MIN_CHARS:
            pages.append(Page(i, clean_text(ocr_done[i]), "ocr"))
        else:
            pages.append(Page(i, ocr_done.get(i, ""), "sin_texto"))
    return pages, reason


def _ocr_pages(reader: Any, todo: list[int], ocr: Ocr, lang: str, cache: Path | None,
               log: Log) -> dict[int, str]:
    done = _load_cache(cache)
    pending = [i for i in todo if i not in done]
    if pending:
        log(f"  OCR: {len(pending)} páginas ({len(done)} ya en caché), {ocr.workers} hilos")
    lock = threading.Lock()
    fh = cache.open("a", encoding="utf-8") if cache else None

    def work(i: int, image: Any) -> None:
        text = clean_text(ocr.read(image, lang)) if image is not None else ""
        with lock:
            done[i] = text
            if fh:
                fh.write(json.dumps({"page": i, "text": text}, ensure_ascii=False) + "\n")
                fh.flush()
            if len(done) % 25 == 0:
                log(f"  OCR: {len(done)}/{len(todo)}")

    try:
        with ThreadPoolExecutor(ocr.workers) as ex:
            running: set[Future] = set()
            for i in pending:
                if len(running) >= ocr.workers * 2:     # acota la memoria de imágenes
                    finished, running = wait(running, return_when=FIRST_COMPLETED)
                    for f in finished:
                        f.result()
                running.add(ex.submit(work, i, _page_image(reader.pages[i - 1])))
            for f in running:
                f.result()
    finally:
        if fh:
            fh.close()
    return done


class _Text(HTMLParser):
    """Texto visible de un XHTML (sin scripts ni estilos), con saltos en bloques."""

    BLOCK = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def _read_member(z: zipfile.ZipFile, name: str) -> bytes:
    info = z.getinfo(name)
    if info.file_size > EPUB_MAX_MEMBER:
        raise ValueError(f"EPUB: {name} demasiado grande")
    return z.read(info)


def epub_pages(path: Path) -> list[Page]:
    """Texto del EPUB en orden de lectura (spine), partido en «páginas» de ~2000 caracteres."""
    with zipfile.ZipFile(path) as z:
        container = ElementTree.fromstring(_read_member(z, "META-INF/container.xml"))
        rootfile = next(el.get("full-path") for el in container.iter()
                        if el.tag.endswith("rootfile"))
        opf = ElementTree.fromstring(_read_member(z, rootfile))
        base = PurePosixPath(rootfile).parent
        manifest = {el.get("id"): el.get("href") for el in opf.iter() if el.tag.endswith("item")}
        spine = [el.get("idref") for el in opf.iter() if el.tag.endswith("itemref")]
        chunks: list[str] = []
        for idref in spine:
            href = manifest.get(idref)
            if not href:
                continue
            member = str(base / href) if str(base) != "." else href
            parser = _Text()
            parser.feed(_read_member(z, member).decode("utf-8", errors="replace"))
            chunks.append(clean_text("".join(parser.parts)))
    pages: list[str] = []
    for chunk in chunks:
        cur = ""
        for para in chunk.split("\n"):
            if cur and len(cur) + len(para) > EPUB_PAGE_CHARS:
                pages.append(cur)
                cur = ""
            cur = f"{cur}\n{para}" if cur else para
        if cur.strip():
            pages.append(cur)
    return [Page(i, t, "texto" if len(t) >= MIN_CHARS else "sin_texto")
            for i, t in enumerate(pages, start=1)]
