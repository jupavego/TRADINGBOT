"""T125: tareas leídas del repo y el inventario de datos, que debe estar en
`docs/ALMACENAMIENTO.md` (código y documento no pueden separarse)."""

from pathlib import Path

from eim.continuity import inventory, tasks

V2 = Path(__file__).resolve().parents[2]


def test_tasks_and_latest_session_by_date(tmp_path):
    (tmp_path / "STATUS.md").write_text(
        "| T01 | A | — | ☑ | x |\n| T02 | B | — | ◐ | y |\n| T03 | C | — | ☐ |  |\n"
        "| T04 | D | — | ☐ |  |\n| no | es | una | fila |\n", encoding="utf-8")
    (tmp_path / "BACKLOG.md").write_text("- uno\n- dos\ntexto\n", encoding="utf-8")
    (tmp_path / "BITACORA.md").write_text(
        "# Bitácora\n\n## 2026-10-30 04:00 UTC · equipo-a · T125\n- **Siguiente paso:** subir\n\n"
        "## 2026-10-29 10:00 UTC · equipo-b · T117\n- **Siguiente paso:** esperar\n",
        encoding="utf-8")                      # tras una unión de git: no cronológico
    t = tasks.read(tmp_path)
    assert (t.count("hecha"), t.count("en curso"), t.count("pendiente")) == (1, 1, 2)
    assert t.by_state["en curso"] == [("T02", "B")] and t.backlog_lines == 2
    assert t.last_session.startswith("2026-10-30 04:00") and t.next_step == "subir"


def test_real_status_parses():
    t = tasks.read(V2.parent / "PLAN")
    assert t.count("hecha") > 50 and t.count("en curso") >= 1


def test_every_inventory_path_is_documented():
    doc = (V2 / "docs" / "ALMACENAMIENTO.md").read_text(encoding="utf-8")
    missing = [i.path for i in inventory.ITEMS if f"`{i.path}`" not in doc]
    assert missing == [], f"añade a docs/ALMACENAMIENTO.md: {missing}"
    assert len({i.path for i in inventory.ITEMS}) == len(inventory.ITEMS)


def test_local_paths(tmp_path):
    by = {i.path: i for i in inventory.ITEMS}
    assert inventory.local_path(by["@EIM_*"], V2) is None
    assert inventory.local_path(by["~/.claude/projects"], V2, tmp_path) == \
        tmp_path / ".claude/projects"
    assert inventory.local_path(by["data/paper.duckdb"], V2) == V2 / "data/paper.duckdb"
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f").write_bytes(b"123")
    assert inventory.size_bytes(tmp_path / "a") == 3
