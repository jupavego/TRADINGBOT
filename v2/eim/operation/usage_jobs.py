"""Qué trabajo de la cola corría dentro del árbol de un `submit` (T149, entregable 3).

El `submit` que coge `runner.lock` se queda de ejecutor y vacía la cola entera, así que todo lo
que corre después cuelga de su árbol y el registro de consumo lo veía con su orden: el 9-nov
`t143-maker` (6,8 GB) salió como `submit --name gate-t143-final`, que había terminado a las
10:38. Aquí se cruza la hora de cada muestra con `data/jobs/log`: si el árbol es el de un
ejecutor (la orden de `eim.operation.jobs … submit` y al menos un hijo) y en ese instante corría
un trabajo, el árbol lleva su nombre e id. Solo lee; nada sale del equipo.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

from eim.operation.usage_foreign import clean_command

EXECUTOR = re.compile(r"eim\.operation\.jobs\b.*\bsubmit\b")
_ENDS = {"termina", "reencolado_por_memoria", "interrumpido", "cancelado_por_memoria"}


def is_executor(tree: dict) -> bool:
    return (tree.get("n") or 0) >= 2 and bool(EXECUTOR.search(tree.get("cmd") or ""))


def _days_with_eve(days: list[str]) -> list[str]:
    """Un trabajo puede haber arrancado el día anterior al primero pedido."""
    if not days:
        return []
    eve = (date.fromisoformat(min(days)) - timedelta(days=1)).isoformat()
    return [eve, *sorted(set(days))]


def load_runs(data_dir: Path, days: Iterable[str]) -> list[dict]:
    """Tramos en que corrió cada trabajo: {id, name, cmd, t0, t1} en ms (t1 None: sin cerrar)."""
    rows: list[dict] = []
    for day in _days_with_eve(list(days)):
        try:
            text = (Path(data_dir) / "jobs" / "log" / f"{day}.jsonl").read_text(
                encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    rows.sort(key=lambda r: r.get("t", 0))
    cmds: dict[str, str] = {}
    open_: dict[str, dict] = {}
    out: list[dict] = []
    for r in rows:
        job, ev = r.get("job"), r.get("event")
        if not job:
            continue
        if ev == "encolado":
            cmds[job] = r.get("cmd") or ""
        elif ev == "arranca":
            open_[job] = {"id": job, "name": r.get("name"), "cmd": clean_command(cmds.get(job)),
                          "t0": r["t"], "t1": None}
            out.append(open_[job])
        elif ev in _ENDS and job in open_:
            open_.pop(job)["t1"] = r["t"]
    return out


def running_at(runs: list[dict], t_ms: int) -> dict | None:
    """El trabajo que corría en ese instante (la cola corre uno a la vez)."""
    for run in reversed(runs):
        if run["t0"] <= t_ms and (run["t1"] is None or t_ms < run["t1"]):
            return run
    return None


def relabel(tree: dict, runs: list[dict], t_ms: int) -> dict:
    """El árbol con el nombre del trabajo que alojaba, si era un ejecutor; si no, tal cual."""
    if not runs or not is_executor(tree) or (run := running_at(runs, t_ms)) is None:
        return tree
    return {**tree, "job": run["name"], "job_id": run["id"], "cmd": run["cmd"],
            "host_cmd": tree.get("cmd")}
