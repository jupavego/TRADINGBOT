"""Genera PLAN/status.js a partir de PLAN/STATUS.md y de la cabecera de cada Txx.md.

Uso:  python PLAN/build_roadmap.py
El archivo roadmap.html lo relee solo cada pocos segundos (funciona abierto con doble clic).
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

PLAN = Path(__file__).resolve().parent
STATE = {"☐": "pending", "◐": "progress", "☑": "done"}
ROW = re.compile(r"^\|\s*(T\d+)\s*\|(.+?)\|(.*?)\|\s*([☐◐☑])\s*\|(.*)\|\s*$")


def head_info(task_id: str) -> dict:
    f = PLAN / f"{task_id}.md"
    if not f.exists():
        return {}
    lines = f.read_text(encoding="utf-8").splitlines()
    info = {}
    if len(lines) > 1:
        m = re.search(r"Esfuerzo:\s*([\wáéíóú-]+)", lines[1])
        if m:
            info["effort"] = m.group(1)
        m = re.search(r"Fase\s+(\d+)", lines[1])
        if m:
            info["phase"] = int(m.group(1))
    for i, ln in enumerate(lines):
        if ln.startswith("## Objetivo"):
            info["goal"] = next((x.strip() for x in lines[i + 1:] if x.strip()), "")
            break
    return info


def main() -> int:
    status = PLAN / "STATUS.md"
    tasks = []
    for ln in status.read_text(encoding="utf-8").splitlines():
        m = ROW.match(ln.strip())
        if not m:
            continue
        tid, title, deps, st, notes = m.groups()
        t = {
            "id": tid,
            "title": re.sub(r"[*`]", "", title).strip(),
            "deps": re.findall(r"T\d+", deps),
            "state": STATE[st],
            "notes": notes.strip(),
        }
        t.update(head_info(tid))
        tasks.append(t)
    payload = {"generated": datetime.now().isoformat(timespec="seconds"), "tasks": tasks}
    out = PLAN / "status.js"
    out.write_text("window.EIM_STATUS = " + json.dumps(payload, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
    done = sum(t["state"] == "done" for t in tasks)
    print(f"status.js: {len(tasks)} tareas, {done} hechas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
