"""Huella del código con que se produjo un resultado (T124): commit de git y hash de `eim/*.py`.

El hash recorre las fuentes Python de `eim/` (sin `web/`), con saltos de línea normalizados, así
que dos equipos con el mismo código dan la misma huella aunque git difiera. Se calcula una vez
por proceso: en un proceso largo (la API) es la del arranque, que es el código que de verdad
corre aunque luego se traiga `main` a la carpeta. La huella dice si el código es otro; si eso
cambia la cifra lo decide `repetir` recalculando.
"""

from __future__ import annotations

import hashlib
import subprocess
from functools import cache
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]          # …/v2/eim
SKIP = {"web", "__pycache__"}
UNKNOWN = {"commit": None, "tree": None, "dirty": None,
           "note": "anterior a T124: no se guardó la huella del código"}


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=PKG, capture_output=True, text=True, timeout=10,
                             check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def tree_hash(pkg: Path = PKG) -> str:
    h = hashlib.sha256()
    for top in sorted(p for p in pkg.iterdir() if p.name not in SKIP):
        files = [top] if top.is_file() else sorted(top.rglob("*.py"))
        for f in files:
            if f.suffix != ".py" or SKIP & set(f.parts):
                continue
            h.update(f.relative_to(pkg).as_posix().encode() + b"\0")
            h.update(f.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()[:16]


@cache
def fingerprint() -> dict:
    """{commit, tree (16 hex), dirty (cambios sin commit en eim/)}."""
    status = _git("status", "--porcelain", "--", ".")
    return {"commit": _git("rev-parse", "HEAD"), "tree": tree_hash(),
            "dirty": None if status is None else bool(status)}


def describe(code: dict | None) -> str:
    if not code or not code.get("tree"):
        return (code or UNKNOWN).get("note") or "sin huella"
    commit = (code.get("commit") or "sin git")[:9]
    return f"{commit} · árbol {code['tree']}" + (" · con cambios sin commit" if code.get("dirty")
                                                   else "")
