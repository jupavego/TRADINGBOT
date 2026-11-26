"""T93 — el escáner no puede llegar a una orden: no importa ejecución, riesgo, papel ni LLM."""

from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "eim"
FILES = sorted((PKG / "scanner").glob("*.py")) + [PKG / "data" / "scanner_market.py",
                                                   PKG / "data" / "scanner_store.py"]
FORBIDDEN = ("eim.execution", "eim.risk", "eim.paper", "eim.operation.cycle", "eim.synthesis",
             "eim.agents.context", "anthropic", "openai")


def _imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_scanner_never_imports_the_order_path():
    assert len(FILES) >= 10
    for f in FILES:
        bad = {m for m in _imports(f) if m.startswith(FORBIDDEN)}
        assert not bad, f"{f.name} importa {bad}"


def test_files_stay_under_300_lines():
    for f in FILES:
        assert len(f.read_text(encoding="utf-8").splitlines()) <= 300, f.name
