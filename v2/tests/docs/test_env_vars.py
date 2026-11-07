"""La tabla de variables de `docs/OPERACION.md` §2 nombra todas las `EIM_*` del código (T121).

Se busca el nombre como texto en `eim/`, `scripts/` y `tests/opt_in.py` (constantes, `os.environ`,
`$env:` de PowerShell, docstrings y mensajes: si un texto le dice a alguien que defina una
variable, también tiene que estar documentada). Un nombre que termina en `_` (`EIM_SHARE_*`) es
un prefijo y basta con que alguna variable documentada empiece por él.
"""
from __future__ import annotations

import re
from pathlib import Path

V2 = Path(__file__).resolve().parents[2]
DOC = V2 / "docs" / "OPERACION.md"
SOURCES = [("eim", "*.py"), ("scripts", "*.py"), ("scripts", "*.ps1"), ("tests", "opt_in.py")]
TOKEN = re.compile(r"\bEIM_[A-Z0-9_]+")


def _used() -> dict[str, set[str]]:
    """Nombre → archivos que lo mencionan."""
    found: dict[str, set[str]] = {}
    for folder, pattern in SOURCES:
        for f in sorted((V2 / folder).rglob(pattern)):
            if ".venv" in f.parts or "node_modules" in f.parts:
                continue
            for name in TOKEN.findall(f.read_text(encoding="utf-8", errors="replace")):
                found.setdefault(name, set()).add(f.relative_to(V2).as_posix())
    return found


def _documented() -> set[str]:
    """Variables de la primera columna de la tabla de §2 (cada una con su nombre completo)."""
    text = DOC.read_text(encoding="utf-8")
    start = text.index("## 2. Variables de entorno")
    end = text.index("\n## ", start + 1)
    names: set[str] = set()
    for line in text[start:end].splitlines():
        cells = line.split("|")
        if line.startswith("|") and len(cells) > 2:
            names.update(TOKEN.findall(cells[1]))
    return names


def test_the_table_is_parsed():
    doc = _documented()
    assert {"EIM_DATA_DIR", "EIM_DUCKDB_MEMORY", "EIM_LIBRARY_LLM"} <= doc
    assert not [n for n in doc if n.endswith("_")], "en la tabla, nombres completos, sin prefijos"


def test_every_variable_the_code_reads_is_documented():
    doc = _documented()
    missing = {}
    for name, files in _used().items():
        known = any(d.startswith(name) for d in doc) if name.endswith("_") else name in doc
        if not known:
            missing[name] = sorted(files)
    assert not missing, ("variables sin fila en docs/OPERACION.md §2 (añádelas con su defecto "
                         f"y su uso): {missing}")


def test_every_documented_variable_still_exists():
    used = _used()
    stale = sorted(n for n in _documented() if n not in used)
    assert not stale, f"docs/OPERACION.md §2 lista variables que ya nadie lee: {stale}"
