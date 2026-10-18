"""Libros sintéticos para los tests de la biblioteca (T52): nunca un libro real."""

from __future__ import annotations

import zipfile
from pathlib import Path


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(path: Path, pages: list[str | None]) -> Path:
    """PDF mínimo válido: una página por elemento; `None` = página sin capa de texto."""
    objs: list[bytes] = []
    n = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, text in enumerate(pages):
        content = b""
        if text:
            lines = " T* ".join(f"({_esc(ln)}) Tj" for ln in text.split("\n"))
            content = f"BT /F1 11 Tf 14 TL 50 740 Td {lines} ET".encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources "
                    f"<< /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for k, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{k} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))
    return path


def make_epub(path: Path, chapters: list[str]) -> Path:
    """EPUB 3 mínimo con un XHTML por capítulo (párrafos separados por línea en blanco)."""
    items = "".join(f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>'
                    for i in range(len(chapters)))
    spine = "".join(f'<itemref idref="c{i}"/>' for i in range(len(chapters)))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                   '<rootfile full-path="OEBPS/content.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf",
                   '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
                   f'version="3.0"><manifest>{items}</manifest><spine>{spine}</spine></package>')
        for i, text in enumerate(chapters):
            paras = "".join(f"<p>{p}</p>" for p in text.split("\n\n"))
            z.writestr(f"OEBPS/c{i}.xhtml",
                       '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><head>'
                       f"<style>p {{ color: red }}</style></head><body>{paras}</body></html>")
    return path
