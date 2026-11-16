"""T169: el examen físico no calcula ni muestra rendimiento (regla 5 de la nota de T167 §3).

Tres guardas: (1) el informe real no tiene ninguna clave ni cabecera de rendimiento; (2) la
guarda salta si alguien añade R neto, acierto o PF; (3) el código del examen no lee del motor los
campos que son resultado (neto, bruto, R, P&L, gemelos, precio o motivo de salida).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from eim.nursery.exam.report import check_no_performance, md_headers, to_markdown

ROOT = Path(__file__).resolve().parents[2]
CODE = sorted((ROOT / "eim" / "nursery" / "exam").glob("*.py")) + [
    ROOT / "scripts" / "t169_examen.py"]
REPORT = ROOT / "reports" / "t169_examen_fisico"
BANNED_ATTRS = {"r", "net", "gross", "pnl_usd", "d_r", "twins", "twin_pnl_usd", "mean_r", "exit",
                "reason", "markout_bps", "balance", "sd_r"}
BANNED_MODULES = {"eim.nursery.book", "eim.nursery.summary", "eim.nursery.desk"}


def _minimal() -> dict:
    ph = {"ideas": 3, "filled": 2, "unfilled": 1, "ops_month": 4.0,
          "ops_month_by_block": [3.0, 5.0],
          "cost_r_mean": 0.12, "hold_h_median": 5.0,
          "pos_days_frac": 0.2, "turnover_month": 3.0,
          "coverage": {"agent_ok": 1.0, "variables": [{"variable": "metrics.regime",
                                                      "with_value": 1.0}]}}
    v = {"band": "intradia", "declared_band": "intradia", "reassigned": False,
         "discarded": False, "reasons": [], "borderline": [], "no_first_team": True,
         "expected_in_term": 24.0, "days_to_verdict": {}}
    return {"prospects": [{"id": "x", "timeframe": "1h", "physics": ph, "verdict": v}],
            "summary_lines": ["resumen"], "checks_lines": ["## Comprobaciones"],
            "mintrl": [{"mu_r": 0.1, "z": 1.645, "ops": 273}], "without_history": {"y": "z"}}


def test_minimal_report_passes_the_guard() -> None:
    data = _minimal()
    check_no_performance(data, to_markdown(data))


@pytest.mark.parametrize("key", ["r_net", "net_r", "R neto", "acierto", "win_rate", "pf",
                                 "profit_factor", "pnl_usd", "gross", "d_r", "twins", "sharpe"])
def test_guard_rejects_performance_keys(key: str) -> None:
    data = _minimal()
    data["prospects"][0]["physics"][key] = 0.5
    with pytest.raises(ValueError, match="rendimiento"):
        check_no_performance(data, to_markdown(data))


@pytest.mark.parametrize("col", ["R neto", "Acierto", "PF", "Beneficio neto", "Gemelos"])
def test_guard_rejects_performance_columns(col: str) -> None:
    data = _minimal()
    md = to_markdown(data) + f"\n| Prospecto | {col} |\n|---|--:|\n| `x` | 0,1 |\n"
    assert col in md_headers(md)
    with pytest.raises(ValueError, match="rendimiento"):
        check_no_performance(data, md)


def test_the_published_report_shows_no_performance() -> None:
    js, md = REPORT.with_suffix(".json"), REPORT.with_suffix(".md")
    assert js.exists() and md.exists(), "falta el informe de T169"
    check_no_performance(json.loads(js.read_text(encoding="utf-8")),
                         md.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", CODE, ids=lambda p: p.name)
def test_exam_code_never_reads_outcomes(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attrs & BANNED_ATTRS, f"{path.name} lee resultados: {attrs & BANNED_ATTRS}"
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not mods & BANNED_MODULES, f"{path.name} importa la cuenta: {mods & BANNED_MODULES}"
