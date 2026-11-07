"""build_roadmap.py: fases sacadas del plan (T121) y status.js sin reescribir si nada cambió."""
from __future__ import annotations

import json
import os
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
MASTER = """# Plan
## Fases y orden
| Fase | Tareas | Resultado |
|---|---|---|
| 0 Cimientos | T01 | Base |
| 1 Agentes | T02 | Agentes |

## Otra sección
| 7 No es una fase | — | — |
"""


def _run(plan: Path) -> str:
    r = subprocess.run([sys.executable, str(plan / "build_roadmap.py"), "--no-publish"],
                       capture_output=True, text=True, check=True)
    return r.stdout


def _task(plan: Path, tid: str, header: str) -> None:
    (plan / f"{tid}.md").write_text(f"# {tid} — Tarea\n{header}\n\n## Objetivo\nAlgo.\n",
                                    encoding="utf-8")


def _plan(tmp_path: Path) -> Path:
    plan = tmp_path / "PLAN"
    plan.mkdir()
    shutil.copy(SCRIPT, plan / "build_roadmap.py")
    (plan / "STATUS.md").write_text(STATUS, encoding="utf-8")
    (plan / "00_MASTER.md").write_text(MASTER, encoding="utf-8")
    _task(plan, "T01", "Fase 0 · Depende: — · Esfuerzo: bajo")
    _task(plan, "T02", "Fase 1 · Depende: T01 · Esfuerzo: medio")
    return plan


def _status(plan: Path) -> dict:
    text = (plan / "status.js").read_text(encoding="utf-8")
    return json.loads(text.split("=", 1)[1].rstrip().removesuffix(";"))


# --- fases sacadas del plan (T121) -----------------------------------------------------------
def test_phases_come_from_task_headers_and_master_names(tmp_path):
    plan = _plan(tmp_path)
    (plan / "STATUS.md").write_text(STATUS + "| T03 | Tercera | — | ☐ | |\n", encoding="utf-8")
    _task(plan, "T03", "Fase 0 · Depende: — · Esfuerzo: bajo")        # tarde, pero en la fase 0
    out = _run(plan)
    assert "3 tareas, 1 hechas, 2 fases" in out and "AVISO" not in out
    assert _status(plan)["phases"] == [{"n": 0, "name": "Cimientos", "ids": ["T01", "T03"]},
                                       {"n": 1, "name": "Agentes", "ids": ["T02"]}]


def test_a_task_without_phase_fails_and_leaves_status_js_alone(tmp_path):
    plan = _plan(tmp_path)
    _run(plan)
    before = (plan / "status.js").read_bytes()
    _task(plan, "T02", "Depende: T01 · Esfuerzo: medio")                # sin «Fase N»
    (plan / "STATUS.md").write_text(STATUS.replace("☐", "☑"), encoding="utf-8")
    r = subprocess.run([sys.executable, str(plan / "build_roadmap.py"), "--no-publish"],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "T02" in r.stderr and "Fase N" in r.stderr
    assert (plan / "status.js").read_bytes() == before
    (plan / "T02.md").unlink()                                          # ni sin archivo
    assert subprocess.run([sys.executable, str(plan / "build_roadmap.py"), "--no-publish"],
                          capture_output=True, text=True).returncode == 1


def test_a_phase_without_name_is_drawn_and_warned(tmp_path):
    plan = _plan(tmp_path)
    _task(plan, "T02", "Fase 7 · Depende: T01 · Esfuerzo: medio")      # la 7 no está en la tabla
    out = _run(plan)
    assert "AVISO" in out and "fase 7" in out
    assert _status(plan)["phases"][-1] == {"n": 7, "name": "Fase 7", "ids": ["T02"]}


def test_a_hand_written_phase_list_in_the_page_still_trips_the_orphan_net(tmp_path):
    plan = _plan(tmp_path)
    (plan / "roadmap.html").write_text('<script>var PHASES=[{n:0,name:"A",ids:["T01"]}];\n'
                                       "var GATES={};</script>", encoding="utf-8")
    out = _run(plan)
    assert "el tablero no dibuja T02" in out and "var PHASES" in out
    (plan / "roadmap.html").write_text("<script>(data.phases||[])</script>", encoding="utf-8")
    assert "no dibuja" not in _run(plan)


def test_real_plan_declares_a_named_phase_for_every_task():
    """El plan de verdad: ninguna tarea sin fase ni fase sin nombre (lo que dibuja el tablero)."""
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        import build_roadmap as br
    finally:
        sys.path.remove(str(SCRIPT.parent))
    rows = [ln for ln in (br.PLAN / "STATUS.md").read_text(encoding="utf-8").splitlines()
            if br.ROW.match(ln.strip())]
    tasks = [{"id": br.ROW.match(ln.strip()).group(1)} for ln in rows]
    for t in tasks:
        t.update(br.head_info(t["id"]))
    assert len(tasks) > 100 and not [t["id"] for t in tasks if "phase" not in t]
    phases, unnamed = br.build_phases(tasks)
    assert not unnamed and not br.orphans(tasks, phases)


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
# Sin variables GIT_* del proceso que lanza la suite (un hook de git las fija y entonces
# init/add/commit tocarían el repositorio real) ni firma o hooks globales del equipo.
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
GIT = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false",
       "-c", "core.hooksPath=/dev/null"]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run([*GIT, *args], cwd=repo, env=ENV, capture_output=True, text=True,
                          check=True).stdout.strip()


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
    return subprocess.run([sys.executable, str(plan / "build_roadmap.py")], env=ENV,
                          capture_output=True, text=True, check=True).stdout


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
    _git(tmp_path, "tag", "origin/main", old)       # un tag homónimo (gana al corto) no engaña
    out = _publish(plan)
    assert "NO actualizado" in out and "origin/main" in out
    assert live.read_bytes() == fresh                                 # la viva sigue al día
    assert "2 tareas, 1 hechas" in out                                # su status.js sí se regenera


def test_without_origin_main_it_publishes_as_before(tmp_path):
    plan, live, _ = _repo(tmp_path)
    assert "roadmap vivo publicado" in _publish(plan) and live.exists()
