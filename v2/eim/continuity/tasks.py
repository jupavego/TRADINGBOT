"""Estado de las tareas leído del repo (T125): `PLAN/STATUS.md`, `PLAN/BACKLOG.md` y la
bitácora de sesiones `PLAN/BITACORA.md`. Es git, así que en cualquier equipo dice lo mismo
que en los demás una vez traído `origin/main`; no depende de la memoria de ninguna sesión.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MARKS = {"☑": "hecha", "◐": "en curso", "☐": "pendiente"}
ENTRY = re.compile(r"^## (\d{4}-\d{2}-\d{2}.*)$")


@dataclass
class Tasks:
    by_state: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    backlog_lines: int = 0
    last_session: str = ""
    next_step: str = ""

    def count(self, state: str) -> int:
        return len(self.by_state.get(state, []))


def read(plan: Path) -> Tasks:
    t = Tasks({v: [] for v in MARKS.values()})
    status = plan / "STATUS.md"
    for line in status.read_text(encoding="utf-8").splitlines() if status.exists() else []:
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 6 or not re.fullmatch(r"T\d+", cells[1]):
            continue
        state = MARKS.get(cells[4])
        if state is None:
            continue
        t.by_state[state].append((cells[1], cells[2]))
    backlog = plan / "BACKLOG.md"
    if backlog.exists():
        t.backlog_lines = sum(1 for ln in backlog.read_text(encoding="utf-8").splitlines()
                              if ln.startswith("- "))
    log = plan / "BITACORA.md"
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    heads = [(m.group(1), i) for i, ln in enumerate(lines) if (m := ENTRY.match(ln))]
    if heads:                       # la más reciente por fecha: tras una unión de git el orden
        t.last_session, i = max(heads)      # del archivo puede no ser cronológico
        for ln in lines[i + 1:]:
            if ln.startswith("## "):
                break
            if ln.lower().startswith("- **siguiente paso"):
                t.next_step = ln.split(":", 1)[-1].strip(" *")
    return t
