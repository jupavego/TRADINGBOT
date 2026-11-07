"""Quién es quién en el registro de consumo, sin línea de órdenes (T127).

La de los servicios de la sesión 0 no se lee desde la sesión del usuario, así que el papel de cada
proceso sale de: el archivo `obs/spool/<papel>.<día>.<pid>.jsonl` de cada proceso Python del EIM,
si se escribió después de nacer el proceso (un PID reutilizado no hereda el papel); el dueño de
los puertos 8000 (API), 5173 (interfaz) y 8765 (hoja de ruta), y el parentesco: un `python.exe`
cuyo único hijo Python tiene papel es su lanzador del venv (casi no reserva memoria) o su
vigilante (`watchdog`, `micro_watchdog`, `hft_watchdog`, que casi no emiten eventos); los
`cmd`/`node` sobre la interfaz y los hijos de un proceso del EIM heredan su papel. «Equipo
despierto» y el icono (PowerShell; apenas gastan) cuentan entre los demás.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from eim.operation.usage_win import Proc

PORT_ROLES = {8000: "api", 5173: "web", 8765: "roadmap"}
NAME_ROLES = {"ollama.exe": "ollama", "ollama_llama_server.exe": "ollama"}
WATCHDOG_OF = {"collector": "micro_watchdog", "hft_collector": "hft_watchdog"}  # si no, watchdog
PYTHON = ("python.exe", "pythonw.exe")
LAUNCHER_MAX_COMMIT = 4 << 20              # el lanzador del venv reserva < 1 MB; Python, > 10 MB
_WEB_UP = ("cmd.exe", "node.exe")          # padres de la interfaz que comparten su papel


def spool_roles(spool: Path, procs: Mapping[int, Proc]) -> dict[int, str]:
    """PID → papel según los archivos de observabilidad de los procesos vivos."""
    out: dict[int, str] = {}
    try:
        entries = list(os.scandir(spool))
    except OSError:
        return out
    for e in entries:
        role, _, pid = e.name.removesuffix(".jsonl").rpartition(".")
        role = role.rpartition(".")[0]
        p = procs.get(int(pid)) if pid.isdigit() else None
        if not role or p is None or p.name.lower() not in PYTHON:
            continue
        try:
            if e.stat().st_mtime >= p.created_s - 1:
                out[p.pid] = role
        except OSError:
            continue
    return out


def attribute(procs: Mapping[int, Proc], spool: Mapping[int, str],
              ports: Mapping[int, int]) -> dict[int, str]:
    """PID → papel de cada proceso del EIM (los que no aparecen son del resto del equipo)."""
    roles = dict(spool)
    for pid, p in procs.items():
        if (r := NAME_ROLES.get(p.name.lower())) and pid not in roles:
            roles[pid] = r
    for port, pid in ports.items():
        if pid in procs and port in PORT_ROLES:
            roles.setdefault(pid, PORT_ROLES[port])
    kids: dict[int, list[int]] = {}
    for pid, p in procs.items():
        par = procs.get(p.ppid)
        if par is not None and p.ppid != pid and par.created <= p.created:  # padre verdadero
            kids.setdefault(p.ppid, []).append(pid)
    changed = True
    while changed:
        changed = False
        for pid, p in procs.items():
            if pid in roles:
                continue
            name, ch = p.name.lower(), kids.get(pid, [])
            up = {roles[c] for c in ch if c in roles}
            py = [c for c in ch if procs[c].name.lower() in PYTHON]
            if name in PYTHON and len(py) == 1 and py[0] in roles:
                child = roles[py[0]]
                roles[pid] = child if p.commit < LAUNCHER_MAX_COMMIT else (  # lanzador del venv
                    WATCHDOG_OF.get(child, "watchdog"))                       # o su vigilante
            elif name in _WEB_UP and up == {"web"}:
                roles[pid] = "web"
            elif p.ppid in roles and pid in kids.get(p.ppid, []):
                roles[pid] = roles[p.ppid]                 # hijo de un proceso del EIM
            else:
                continue
            changed = True
    return roles
