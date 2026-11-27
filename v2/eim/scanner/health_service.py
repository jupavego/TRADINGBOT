"""Revisión de salud multiactivo tras cada pasada (T102): salud, despliegue, avisos y eventos.

`check` es lo único con E/S: lee la vista y el estado del escáner, calcula la salud (`health.py`),
aplica una revisión del despliegue gradual (`rollout.py`), emite los avisos que cambian de estado
(`health_alerts.py`) por los canales locales y manda los eventos por lotes al Observatorio
(`obs_batch.py`). Deja `data/scanner/health.json` y `data/scanner/rollout.json` (escritura
atómica), que es lo que leen la API y el panel. Lo llaman la pasada de agentes
(`deep_service.deep_pass`) y `python -m eim.scanner health` (la tarea diaria, aunque la pasada
falle: así un escáner que no corre acaba en «obsoleto» y avisa).

Nunca tumba una pasada: cualquier fallo de la revisión queda en el observatorio y se sigue.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from eim.data.scanner_view import read_view
from eim.observability import hooks_service
from eim.scanner import health, health_alerts, obs_batch, rollout
from eim.scanner.params import DEFAULT_PARAMS, ScannerParams

HEALTH_FILE, ROLLOUT_FILE, STATUS_FILE = "health.json", "rollout.json", "status.json"
COMPONENT = "scanner.health"
RECENT_MAX = 20
VERDICTS = ("publicable", "en observación", "rechazada", "no aplica")   # contrato de T101


def scanner_dir(data_dir: str | Path) -> Path:
    return Path(data_dir) / "scanner"


def read_json(path: Path) -> dict | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def write_json(path: Path, obj: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def read_health(data_dir: str | Path) -> dict | None:
    return read_json(scanner_dir(data_dir) / HEALTH_FILE)


def read_rollout(data_dir: str | Path) -> dict | None:
    return read_json(scanner_dir(data_dir) / ROLLOUT_FILE)


def t101_cells(reports_dir: Path) -> dict:
    """Celdas de la matriz agente × clase de T101 (`reports/multiasset_validation_*.json`), la
    más reciente: por clase, el mejor veredicto de sus celdas. Sin informe → no disponible."""
    files = sorted(reports_dir.glob("multiasset_validation_*.json")) if reports_dir.exists() \
        else []
    if not files:
        return {"available": False, "reason": "T101 aún no publicó su matriz"}
    d = read_json(files[-1]) or {}
    best: dict[str, str] = {}
    for c in d.get("cells") or []:
        v, cls = c.get("verdict"), c.get("asset_class")
        if v in VERDICTS and cls and (cls not in best or
                                      VERDICTS.index(v) < VERDICTS.index(best[cls])):
            best[cls] = v
    return {"available": True, "file": files[-1].name, "cells": best}


def gates(data_dir: str | Path) -> dict:
    """Lo que el despliegue necesita saber de fuera: T101, y si T96 y T103 ya existen."""
    from eim.observability import catalog

    def built(cid: str) -> bool:
        comp = catalog.get(cid)
        return comp is not None and comp.built == "construido"

    return {"t101": t101_cells(Path(data_dir).parent / "reports"),
            "t96_built": built("scanner.portfolio"), "t103_built": built("scanner.paper_adapter")}


def default_sinks(data_dir: str | Path) -> list[Callable]:
    """Globo de Windows (`EIM_NOTIFY=0` lo apaga), registro JSONL de la operación y observatorio."""
    from eim.operation.notify import JsonLog, WindowsToast

    log = JsonLog(Path(data_dir) / "operation" / "logs")

    def obs(a) -> None:
        hooks_service.service_event(COMPONENT, a.title, status="ok" if a.resolved else
                                    "degraded", detail={"key": a.key, "level": a.level})

    return [WindowsToast(), log.alert_sink, obs]


def summary(state: Mapping) -> dict:
    """Lo que el panel enseña del despliegue: nivel, actividad y qué falta, por unidad."""
    return {k: {f: u.get(f) for f in ("kind", "id", "level", "active", "reason", "next",
                                      "good", "bad", "level_since")}
            for k, u in sorted((state.get("units") or {}).items())}


def check(data_dir: str | Path, *, view: Mapping | None = None, status: Mapping | None = None,
          excl_by_class: Mapping | None = None, now: int | None = None,
          sinks: Iterable[Callable] | None = None, emit_events: bool = True,
          params: ScannerParams = DEFAULT_PARAMS) -> dict:
    """Una revisión completa; devuelve la salud tal como queda en `health.json`."""
    now = int(time.time() * 1000) if now is None else int(now)
    sd = scanner_dir(data_dir)
    view = view if view is not None else read_view(data_dir)
    status = status if status is not None else read_json(sd / STATUS_FILE)
    h = health.build(view, status, now, excl_by_class=excl_by_class, params=params)
    state, changes = rollout.evaluate(read_rollout(data_dir), h, view, gates(data_dir), now)
    write_json(sd / ROLLOUT_FILE, state)
    prev = read_health(data_dir) or {}
    alerts, active = health_alerts.transitions(prev.get("alerts_active") or {},
                                               health_alerts.conditions(h), now)
    for a in alerts:
        for sink in (default_sinks(data_dir) if sinks is None else sinks):
            try:
                sink(a)
            except Exception as exc:  # noqa: BLE001 - un canal roto no para la revisión
                hooks_service.service_error(COMPONENT, exc)
    t0 = time.perf_counter()
    events = obs_batch.build(view, h, state, changes)
    build_ms = (time.perf_counter() - t0) * 1000
    info = obs_batch.emit_batch(events) if emit_events else {"events": len(events)}
    info["build_ms"] = round(build_ms, 3)
    info["within"] = info.get("within", True) and \
        build_ms + info.get("emit_ms", 0) <= obs_batch.MAX_CYCLE_OVERHEAD_MS
    h.update(alerts_active=active,
             alerts_recent=([a.to_json() for a in alerts] + list(prev.get("alerts_recent")
                                                                 or []))[:RECENT_MAX],
             rollout={"units": summary(state), "changes": changes,
                      "levels": list(rollout.LEVELS)},
             observability=info)
    write_json(sd / HEALTH_FILE, h)
    return h


def safe_check(data_dir: str | Path, **kw) -> dict | None:
    """`check` sin propagar: lo usa la pasada de agentes (la revisión nunca la tumba)."""
    try:
        return check(data_dir, **kw)
    except Exception as exc:  # noqa: BLE001 - se dice en el observatorio y la pasada sigue
        hooks_service.service_error(COMPONENT, f"revisión de salud: {type(exc).__name__}: {exc}")
        return None
