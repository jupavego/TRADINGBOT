"""build_roadmap.py no reescribe status.js si el plan no cambió (así `git pull` no se frena)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "PLAN" / "build_roadmap.py"
STATUS = """| Tarea | Título | Dep. | Estado | Notas |
|---|---|---|---|---|
| T01 | Primera | — | ☑ | hecha |
| T02 | Segunda | T01 | ☐ | |
"""


def _run(plan: Path) -> str:
    r = subprocess.run([sys.executable, str(plan / "build_roadmap.py"), "--no-publish"],
                       capture_output=True, text=True, check=True)
    return r.stdout


def _plan(tmp_path: Path) -> Path:
    plan = tmp_path / "PLAN"
    plan.mkdir()
    shutil.copy(SCRIPT, plan / "build_roadmap.py")
    (plan / "STATUS.md").write_text(STATUS, encoding="utf-8")
    return plan


def test_unchanged_plan_leaves_status_js_byte_identical(tmp_path):
    plan = _plan(tmp_path)
    first_out = _run(plan)
    assert "2 tareas, 1 hechas" in first_out and "sin cambios" not in first_out
    first = (plan / "status.js").read_bytes()
    out = _run(plan)
    assert "sin cambios" in out
    assert (plan / "status.js").read_bytes() == first          # ni la marca de hora cambia


def test_changed_plan_rewrites_status_js(tmp_path):
    plan = _plan(tmp_path)
    _run(plan)
    before = (plan / "status.js").read_bytes()
    (plan / "STATUS.md").write_text(STATUS.replace("| T02 | Segunda | T01 | ☐ |",
                                                   "| T02 | Segunda | T01 | ☑ |"),
                                    encoding="utf-8")
    assert "2 tareas, 2 hechas" in _run(plan)
    assert (plan / "status.js").read_bytes() != before


def test_missing_or_broken_status_js_is_regenerated(tmp_path):
    plan = _plan(tmp_path)
    _run(plan)
    (plan / "status.js").write_text("esto no es un status.js", encoding="utf-8")
    assert "2 tareas" in _run(plan) and "window.EIM_STATUS" in (plan / "status.js").read_text(
        encoding="utf-8")
