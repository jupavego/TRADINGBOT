"""Qué son los programas ajenos que cargan el equipo (T141, entregable 1).

El registro de consumo guardaba solo el nombre, y «12 `python.exe`» no decía de quién eran. Aquí
se agrupan los procesos ajenos al EIM por árbol, porque un conjunto de 7 trabajadores al 10 % pesa
como un programa al 70 % y ninguno pasaría por sí solo de un umbral. De cada árbol que pasa de
`MIN_CPU` o `MIN_RAM_MB` se guarda la línea de órdenes de su raíz, recortada y sin secretos, y su
carpeta de trabajo. Se lee una sola vez por proceso.

Esto se queda en `data/usage`, que no viaja (`continuity/inventory.py`): ni el registro de
operación ni el observatorio reciben estas líneas, porque esos sí entran en las copias.
"""

from __future__ import annotations

import ntpath
import re
from collections.abc import Callable, Mapping

from eim.operation import usage_win
from eim.operation.usage_win import Proc

# Los que se identifican: el nombre de chrome o claude ya dice qué son, y sus líneas de órdenes son
# largas y pueden llevar direcciones privadas. Blender y node aparecen en los bloqueos de T141.
IDENTIFY = frozenset({"python.exe", "pythonw.exe", "blender.exe", "node.exe"})
MIN_CPU = 5.0        # % del equipo: una quinta parte de un núcleo, con 4 núcleos
MIN_RAM_MB = 300     # lo bastante para ser un programa de verdad y no una orden suelta
MAX_TREES = 5
CMD_MAX, CWD_MAX = 160, 80

_FIRST = re.compile(r'^\s*(?:"([^"]+)"|(\S+))')
_INLINE = re.compile(r"\s(-c|-e|--eval)\s.*$", re.S)   # código en línea: se queda fuera entero
_SECRET = re.compile(
    r"(?i)([\w-]*(?:token|secret|passw(?:or)?d|pwd|api[-_]?key|auth|credential|cookie|bearer)"
    r"[\w-]*)(=|\s+)(\"[^\"]*\"|'[^']*'|\S+)")
_URL = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)(?:[^/\s@]+@)?([^/\s?#]+)([^\s?#]*)[^\s]*")
_OPAQUE = re.compile(r"\b[A-Za-z0-9+_-]{32,}={0,2}")   # claves y fichas pegadas sin nombre


def clean_command(cmd: str | None, limit: int = CMD_MAX) -> str | None:
    """Línea de órdenes para guardar: el programa sin su ruta, sin código en línea, sin secretos
    ni el resto de una dirección web, y recortada."""
    if not cmd:
        return None
    m = _FIRST.match(cmd)
    if m:
        cmd = ntpath.basename(m.group(1) or m.group(2)) + cmd[m.end():]
    cmd = _INLINE.sub(r" \1 …", cmd)
    cmd = _SECRET.sub(r"\1\2***", cmd)
    cmd = _URL.sub(r"\1\2\3", cmd)
    cmd = " ".join(_OPAQUE.sub("***", cmd).split())
    return cmd if len(cmd) <= limit else cmd[:limit - 1] + "…"


def clean_dir(path: str | None, limit: int = CWD_MAX) -> str | None:
    """Carpeta de trabajo sin la barra final; si no cabe, se queda el final, que es lo que dice
    de qué proyecto es."""
    if not path:
        return None
    path = path.rstrip("\\/")
    return path if len(path) <= limit else "…" + path[-(limit - 1):]


def _mb(b: float) -> float:
    return round(b / (1 << 20), 1)


def trees(procs: Mapping[int, Proc], roles: Mapping[int, str],
          cpu_of: Callable[[Proc], float]) -> list[dict]:
    """Árboles de procesos ajenos que pasan del umbral, de más a menos CPU. La raíz es el
    antepasado ajeno e identificable más lejano (el que da nombre al conjunto)."""
    def root(p: Proc) -> Proc:
        seen = {p.pid}
        while ((up := procs.get(p.ppid)) is not None and up.pid not in seen
               and up.pid not in roles and up.created <= p.created
               and up.name.lower() in IDENTIFY):
            seen.add(up.pid)
            p = up
        return p

    groups: dict[int, dict] = {}
    for pid, p in procs.items():
        if pid in roles or p.name.lower() not in IDENTIFY:
            continue
        top = root(p)
        g = groups.setdefault(top.pid, {"pid": top.pid, "name": top.name, "n": 0, "cpu": 0.0,
                                        "ram": 0, "commit": 0, "prio": 0})
        g["n"] += 1
        g["cpu"] += cpu_of(p)
        g["ram"] += p.ram
        g["commit"] += p.commit
        g["prio"] = max(g["prio"], p.prio)
    big = [g for g in groups.values() if g["cpu"] >= MIN_CPU or g["ram"] >> 20 >= MIN_RAM_MB]
    big.sort(key=lambda g: (-g["cpu"], -g["ram"]))
    return [{"pid": g["pid"], "name": g["name"], "n": g["n"], "cpu": round(g["cpu"], 2),
             "ram_mb": _mb(g["ram"]), "commit_mb": _mb(g["commit"]), "prio": g["prio"]}
            for g in big[:MAX_TREES]]


class Identifier:
    """Añade la orden y la carpeta a cada árbol; recuerda lo leído mientras el proceso viva, así
    que el coste es abrir cada proceso una vez, y solo los que pasan del umbral."""

    def __init__(self, backend=usage_win) -> None:
        self.backend = backend
        self._seen: dict[tuple[int, int], dict] = {}

    def _read(self, pid: int) -> dict:
        try:
            return {"cmd": clean_command(self.backend.command_line(pid)),
                    "cwd": clean_dir(self.backend.working_dir(pid))}
        except (OSError, ValueError, AttributeError):   # sin permiso o ya terminó: queda sin nombre
            return {"cmd": None, "cwd": None}

    def identify(self, procs: Mapping[int, Proc], roles: Mapping[int, str],
                 cpu_of: Callable[[Proc], float]) -> list[dict]:
        out = trees(procs, roles, cpu_of)
        for t in out:
            key = (t["pid"], procs[t["pid"]].created)
            if key not in self._seen:
                self._seen[key] = self._read(t["pid"])
            t.update(self._seen[key])
        self._seen = {k: v for k, v in self._seen.items()
                      if (p := procs.get(k[0])) is not None and p.created == k[1]}
        return out
