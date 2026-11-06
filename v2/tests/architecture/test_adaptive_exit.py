"""T135 — Ningún agente escribe stops: el motor de la posición no puede ni importarlos.

§4.2 de `T129_sl_dinamico.md`: los agentes solo eligen entre valores pre-registrados y solo a través
de `ExitFeatures`. Hoy ni eso: los rasgos salen de las velas. Se comprueba sobre el código fuente,
sin ejecutarlo, para que una importación nueva rompa aquí y no en una revisión.
"""

from __future__ import annotations

import ast
from pathlib import Path

import eim
from eim.paper.params import PROFILES

PAPER = Path(eim.__file__).parent / "paper"
ENGINE = [PAPER / "adaptive.py", PAPER / "adaptive_params.py",
          *sorted((PAPER / "exits").glob("*.py"))]
FORBIDDEN = ("eim.agents", "eim.forecast", "eim.synthesis", "eim.llm", "anthropic", "openai",
             "httpx", "requests", "duckdb")
# El banco lee copias de datos para medir (`exits/run.py`); el motor del libro no toca nada de eso.
BENCH_ONLY = {"run.py", "bench.py", "experiment.py", "report.py", "exits_report.py",
              "risk_report.py", "risk_study.py", "oracle_report.py"}


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_the_position_engine_cannot_import_agents_llms_or_io():
    for path in ENGINE:
        if path.name in BENCH_ONLY:
            continue
        bad = {m for m in _imports(path) if m.startswith(FORBIDDEN)}
        assert not bad, f"{path.name} importa {sorted(bad)}"


def test_no_profile_is_switched_on():
    """Encender una salida es una decisión ◆ con su pre-registro, no un cambio de código."""
    assert not [p.id for p in PROFILES if p.exit_mode == "adaptativo" or p.adaptive is not None]
