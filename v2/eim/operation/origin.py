"""De qué checkout y desde cuándo corre este proceso (T120).

Los servicios se llegaron a lanzar desde un worktree en vez de la carpeta principal y nadie lo
notaba (`PLAN/notas/auditoria_modulos_2026-10-19.md`). Cada latido lleva ahora `checkout` (la
carpeta `v2/` del código que corre) y `proc_started_at`; `GET /v2/health` y
`servicio_continuo.ps1` los comparan con la carpeta que debería mandar.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

CHECKOUT = str(Path(__file__).resolve().parents[2])   # .../v2 del código que corre
STARTED_MS = int(time.time() * 1000)                  # al importar: arranque del proceso


def stamp(row: dict) -> dict:
    """El latido con su origen; lo que ya traiga el latido manda."""
    return {"checkout": CHECKOUT, "proc_started_at": STARTED_MS, "pid": os.getpid(), **row}


def same_checkout(a: str | None, b: str | None) -> bool:
    """¿Dos rutas de checkout son la misma carpeta? (sin distinguir mayúsculas en Windows)."""
    if not a or not b:
        return False
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
