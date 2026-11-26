"""T93/T94 — el escáner no puede llegar a una orden: no importa ejecución, riesgo, papel ni LLM.

T94 corre los agentes elegibles y la síntesis existente (`deep.py`), así que la síntesis deja de
estar prohibida **solo ahí**; el resto del escáner sigue sin tocarla. Y al revés: ningún módulo de
riesgo, ejecución, papel ni del ciclo de operación importa el escáner ni sus oportunidades.
"""

from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "eim"
FILES = sorted((PKG / "scanner").glob("*.py")) + [
    PKG / "data" / "scanner_market.py", PKG / "data" / "scanner_store.py",
    PKG / "data" / "scanner_view.py", PKG / "core" / "opportunity.py",
    PKG / "api" / "scanner.py"]
FORBIDDEN = ("eim.execution", "eim.risk", "eim.paper", "eim.operation.cycle", "eim.synthesis",
             "eim.agents.context", "anthropic", "openai")
#: T94: la síntesis existente, sin cambios, solo en la activación de agentes.
ALLOWED = {"deep.py": ("eim.synthesis",)}
DOWNSTREAM = ("execution", "risk", "paper")


def _imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_scanner_never_imports_the_order_path():
    assert len(FILES) >= 15
    for f in FILES:
        ok = ALLOWED.get(f.name, ())
        bad = {m for m in _imports(f) if m.startswith(FORBIDDEN) and not m.startswith(ok)}
        assert not bad, f"{f.name} importa {bad}"


def test_nothing_downstream_consumes_the_scanner():
    files = [f for d in DOWNSTREAM for f in (PKG / d).rglob("*.py")]
    files += [PKG / "operation" / "cycle.py"]
    assert len(files) > 20
    for f in files:
        bad = {m for m in _imports(f)
               if m.startswith(("eim.scanner", "eim.core.opportunity", "eim.api.scanner"))}
        assert not bad, f"{f.relative_to(PKG)} importa {bad}"


def test_files_stay_under_300_lines():
    for f in FILES:
        assert len(f.read_text(encoding="utf-8").splitlines()) <= 300, f.name
