"""T131 — el comparador con el informe de T111 (`scripts/t131_t111_diff.py`).

Comprueba que detecta una diferencia real, que no inventa diferencias por el ruido de coma
flotante y que dice cuando a un informe le falta un escenario que el otro sí tiene.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SPEC = Path(__file__).resolve().parents[3] / "scripts" / "t131_t111_diff.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("t131_t111_diff", SPEC)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def metrics(net: float = 100.0, n: int = 10) -> dict:
    return {"n": n, "wins": 6, "losses": n - 6, "win_rate": 0.6, "net": net, "net_won": 200.0,
            "net_lost": -100.0, "pf": 2.0, "expectancy_usd": net / n, "expectancy_r": 0.1,
            "avg_win_r": 0.5, "avg_loss_r": -0.4, "max_dd_r": 1.5}


def report(net: float = 100.0, extra: bool = False) -> dict:
    prof = {}
    for pid in ("conservador", "moderado", "agresivo"):
        b = {"B 0.1 R (encargo)": {"metrics": metrics(net)}}
        if extra:
            b["B 0.5 R"] = {"metrics": metrics(net)}
        prof[pid] = {"A": {"metrics": metrics(net)}, "B": b}
    seg = {"profiles": prof}
    return {"meta": {"commit": "abc", "ideas": 100},
            "segments": {"fuera": seg, "dentro": seg}}


def test_identical_reports_show_no_differences(mod):
    out = mod.diff_segment(report(), report(), "fuera")
    assert len(out) == 6                       # 3 perfiles × (A + 1 variante de B)
    assert all(v["equal"] for v in out.values())


def test_a_real_difference_is_reported_with_its_field(mod):
    out = mod.diff_segment(report(100.0), report(101.0), "fuera")
    bad = [v for v in out.values() if not v["equal"]]
    assert len(bad) == 6
    fields = {d["field"] for d in bad[0]["diffs"]}
    assert "net" in fields and "expectancy_usd" in fields


def test_floating_point_noise_is_not_a_difference(mod):
    assert mod.compare(metrics(100.0), metrics(100.0 + 1e-12)) == []
    assert mod.compare(metrics(100.0), metrics(100.001)) != []


def test_a_missing_scenario_is_named_not_ignored(mod):
    out = mod.diff_segment(report(), report(extra=True), "fuera")
    missing = {k: v for k, v in out.items() if v.get("missing_in")}
    assert len(missing) == 3                   # «B 0.5 R» solo está en el nuevo
    assert all(v["missing_in"] == "viejo" for v in missing.values())


def test_the_comparison_renders_and_says_which_segment_must_match(mod):
    res = {"old": "a.json", "new": "b.json", "old_commit": "abc", "new_commit": "def",
           "old_ideas": 10, "new_ideas": 11,
           "segments": {"fuera": mod.diff_segment(report(), report(), "fuera")}}
    md = mod.render(res)
    assert "6 de 6 escenarios idénticos" in md
    assert "El tramo «fuera» es el que tiene que coincidir" in md
