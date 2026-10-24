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


# --- publicación en la carpeta viva solo desde ramas al día con origin/main ------------------
def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=repo,
                          capture_output=True, text=True, check=True).stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, Path, str]:
    """Repo con PLAN/ y un commit; `v2/data/roadmap_live/` es su carpeta viva."""
    plan = _plan(tmp_path)
    (plan / "roadmap.html").write_text("<html></html>", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "a")
    return plan, tmp_path / "v2" / "data" / "roadmap_live" / "status.js", _git(
        tmp_path, "rev-parse", "HEAD")


def _publish(plan: Path) -> str:
    return subprocess.run([sys.executable, str(plan / "build_roadmap.py")], capture_output=True,
                          text=True, check=True).stdout


def test_publishes_from_a_branch_that_contains_origin_main(tmp_path):
    plan, live, head = _repo(tmp_path)
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", head)
    assert "roadmap vivo publicado" in _publish(plan)
    assert live.read_bytes() == (plan / "status.js").read_bytes()


def test_a_branch_behind_origin_main_does_not_overwrite_the_live_roadmap(tmp_path):
    """El caso de T83: otra rama, creada antes de la fusión, la devolvía a «pendiente»."""
    plan, live, old = _repo(tmp_path)
    (plan / "STATUS.md").write_text(STATUS.replace("| T02 | Segunda | T01 | ☐ |",
                                                   "| T02 | Segunda | T01 | ☑ |"),
                                    encoding="utf-8")
    _git(tmp_path, "commit", "-q", "-am", "T02 fusionada")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert "roadmap vivo publicado" in _publish(plan)
    fresh = live.read_bytes()
    _git(tmp_path, "checkout", "-q", "-b", "rama-vieja", old)        # rama de antes de la fusión
    out = _publish(plan)
    assert "NO actualizado" in out and "origin/main" in out
    assert live.read_bytes() == fresh                                 # la viva sigue al día
    assert "2 tareas, 1 hechas" in out                                # su status.js sí se regenera


def test_without_origin_main_it_publishes_as_before(tmp_path):
    plan, live, _ = _repo(tmp_path)
    assert "roadmap vivo publicado" in _publish(plan) and live.exists()
