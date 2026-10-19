"""Ganchos de los servicios en segundo plano (T74): latido, cadencia real y errores.

`beat` emite un `heartbeat` cada vez que un servicio completa una vuelta y anota la cadencia
REAL desde el latido anterior (la esperada está en el catálogo). `service_error` emite un
`alert` de error. `fetch_*` registra la descarga de datos de un proveedor (`data_fetch`).
Ninguna función lanza (`safe`).
"""

from __future__ import annotations

import threading
import time
from typing import Any

from eim.core import Mode
from eim.observability.emit import emit
from eim.observability.events import new_run_id
from eim.observability.hooks import safe

_last_beat: dict[str, float] = {}
_skipped: dict[str, int] = {}           # vueltas que el muestreo no emitió desde el último latido
_last_err: dict[str, float] = {}
_lock = threading.Lock()


@safe
def beat(component_id: str, *, status: str = "ok", detail: dict[str, Any] | None = None,
         duration_ms: float | None = None, mode: Mode | None = None,
         min_interval_s: float = 0.0) -> None:
    """Latido de un servicio. `min_interval_s` > 0 muestrea los de alta frecuencia (como
    máximo un evento cada tanto); `detail.runs` cuenta las vueltas reales desde el evento
    anterior, así la cadencia real es `interval_s / runs` aunque se muestree."""
    now = time.monotonic()
    with _lock:
        prev = _last_beat.get(component_id)
        if prev is not None and now - prev < min_interval_s:
            _skipped[component_id] = _skipped.get(component_id, 0) + 1
            return
        _last_beat[component_id] = now
        runs = _skipped.pop(component_id, 0) + 1
    d = dict(detail or {})
    if prev is not None:
        d["interval_s"] = round(now - prev, 1)
        d["runs"] = runs
    emit("heartbeat", component_id, status=status, run_id=new_run_id(),  # type: ignore[arg-type]
         duration_ms=duration_ms, detail=d, mode=mode)


@safe
def service_error(component_id: str, error: BaseException | str, *,
                  detail: dict[str, Any] | None = None, mode: Mode | None = None,
                  min_interval_s: float = 0.0) -> None:
    """Error de un servicio. `min_interval_s` evita inundar si falla en cada vuelta."""
    if min_interval_s > 0:
        now = time.monotonic()
        with _lock:
            prev = _last_err.get(component_id)
            if prev is not None and now - prev < min_interval_s:
                return
            _last_err[component_id] = now
    msg = f"{type(error).__name__}: {error}" if isinstance(error, BaseException) else str(error)
    emit("alert", component_id, status="error", run_id=new_run_id(),
         detail={**(detail or {}), "error": msg[:200]}, mode=mode)


@safe
def service_event(component_id: str, what: str, *, status: str = "ok",
                  detail: dict[str, Any] | None = None) -> None:
    """Hecho puntual de un servicio (reinicio del vigilante, copia hecha…)."""
    emit("alert", component_id, status=status, run_id=new_run_id(),  # type: ignore[arg-type]
         detail={**(detail or {}), "what": what})


@safe
def fetch_done(source: str, symbol: str, timeframe: str, step_ms: int, out: dict,
               gaps: list, last_close: int | None, now: int, duration_ms: float) -> None:
    """Descarga de velas de un proveedor: fuente, cobertura real (huecos) y antigüedad."""
    missing = sum((g1 - g0) // step_ms + 1 for g0, g1 in gaps)
    total = out["total"]
    cov = total / (total + missing) if total + missing else None
    emit("data_fetch", "data.binance_rest", run_id=new_run_id(), source=source[:120],
         coverage=cov, status="ok" if not gaps else "degraded", duration_ms=duration_ms,
         detail={"symbol": symbol, "timeframe": timeframe, "fetched": out["fetched"],
                 "total": total, "gaps": len(gaps),
                 "age_min": round((now - last_close) / 60_000) if last_close else None})


@safe
def fetch_failed(source: str, symbol: str, timeframe: str, error: BaseException) -> None:
    emit("data_fetch", "data.binance_rest", status="error", run_id=new_run_id(),
         source=source[:120], detail={"symbol": symbol, "timeframe": timeframe,
                                      "error": f"{type(error).__name__}: {error}"[:200]})
