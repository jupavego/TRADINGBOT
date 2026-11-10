"""Estado del recolector de microestructura (T104): `GET /v2/micro/status`, solo lectura.

Lee el latido y el disco de `data/micro/` (sin tocar la red ni el agente). `state`, `label`,
`reason` y `age_s` salen de `health.collector_state` (T120), la misma tabla que usan el vigilante,
la esfera y el RUNBOOK; más MB/día por tipo y espacio libre.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter

from eim.data.collectors import health


def micro_status(root: Path | str, now_ms: int, symbol: str = health.DEFAULT_SYMBOL) -> dict:
    st = health.collector_state(root, now_ms, symbol)
    if st["state"] == "unidad_ausente":          # sin unidad no hay latido ni disco que leer
        return {**st, "heartbeat": None, "started_at": None, "disk": None,
                "symbol": symbol.upper(), "problems": health.problems(root, now_ms, symbol=symbol)}
    hb = health.read_heartbeat(root, symbol)
    return {**st, "heartbeat": hb,
            "started_at": hb.get("started_at") if hb else None,
            "disk": health.disk_report(root), "symbol": symbol.upper(),
            "problems": health.problems(root, now_ms, symbol=symbol)}


def build_micro_router(root: Path | str,
                       clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> APIRouter:
    r = APIRouter(prefix="/v2/micro", tags=["micro"])

    @r.get("/status")
    def status(symbol: str = health.DEFAULT_SYMBOL) -> dict:
        return micro_status(root, clock(), symbol)

    return r
