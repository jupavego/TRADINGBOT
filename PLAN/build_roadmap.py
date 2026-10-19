"""Genera PLAN/status.js a partir de PLAN/STATUS.md y de la cabecera de cada Txx.md.

Uso:  python PLAN/build_roadmap.py [--no-publish]
Además publica roadmap.html y status.js en la carpeta viva que sirve el acceso directo del escritorio.
El archivo roadmap.html lo relee solo cada pocos segundos (funciona abierto con doble clic).
"""
import json
import re
import shutil
import subprocess
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


def live_dir() -> Path | None:
    """Carpeta viva `v2/data/roadmap_live/` del checkout principal (ignorada por git).

    El acceso directo del escritorio sirve esa carpeta; así la hoja de ruta refleja el trabajo de
    cualquier worktree sin ensuciar `main` ni arrancar servidores nuevos.
    """
    try:
        out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             cwd=PLAN, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(out).parent / "v2" / "data" / "roadmap_live"


def publish(tasks: list) -> None:
    """Copia roadmap.html y status.js a la carpeta viva, salvo que sea de un plan más viejo."""
    dest = live_dir()
    if dest is None:
        return
    dest.mkdir(parents=True, exist_ok=True)
    cur = dest / "status.js"
    if cur.exists():
        n_live = len(re.findall(r'"id":\s*"T\d+"', cur.read_text(encoding="utf-8")))
        if n_live > len(tasks):
            print(f"roadmap vivo NO actualizado: tiene {n_live} tareas y esta rama {len(tasks)} (plan más viejo)")
            return
    for name in ("roadmap.html", "status.js"):
        shutil.copyfile(PLAN / name, dest / name)
    print(f"roadmap vivo publicado en {dest}")


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
    if "--no-publish" not in sys.argv:
        publish(tasks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
