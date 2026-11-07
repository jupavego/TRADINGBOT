"""`GET /v2/obs/queues` (T123): estado de cada frontera de la tubería, solo lectura.

Por frontera declarada en `eim.observability.queues.FRONTIERS`: su tope, su política y, por cada
proceso que la cuenta, el último informe recibido (descartes, esperas, ocupación máxima y última
causa, exactos desde `since_ms`). Una frontera sin informe reciente sale con `no_data` y el
motivo: nunca se rellena con ceros.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException

from eim.observability import queues
from eim.observability.store import ObsStore

WINDOW_MS = 86_400_000                     # informes de las últimas 24 h
STALE_S = 2.5 * queues.KEEPALIVE_S         # sin informe en 2,5 renovaciones → sin datos recientes


def latest_reports(store: ObsStore, now_ms: int) -> list[dict]:
    """Último informe por (frontera, proceso) en la ventana."""
    rows = store.query(
        "SELECT ts_utc, process, component_id, status, source, coverage, detail FROM events "
        "WHERE kind = 'heartbeat' AND ts_utc >= ? AND detail LIKE '%\"queue\":%' "
        "QUALIFY row_number() OVER (PARTITION BY json_extract_string(detail, '$.queue'), "
        "process ORDER BY ts_utc DESC) = 1", [now_ms - WINDOW_MS])
    for r in rows:
        r["detail"] = json.loads(r["detail"]) if r.get("detail") else {}
    return rows


def frontiers_view(rows: list[dict], now_ms: int, component_id: str | None = None) -> list[dict]:
    by: dict[str, list[dict]] = {}
    for r in rows:
        d = r["detail"]
        by.setdefault(str(d.get("queue")), []).append({
            "process": r["process"], "ts_utc": r["ts_utc"], "status": r["status"],
            "age_s": round((now_ms - r["ts_utc"]) / 1000, 1),
            "stale": now_ms - r["ts_utc"] > STALE_S * 1000,
            "source": r["source"], "coverage": r["coverage"],
            **{k: d.get(k) for k in ("capacity", "occupancy", "max_occupancy", "dropped",
                                     "dropped_new", "held", "held_new", "held_s", "last_cause",
                                     "last_ms", "since_ms", "pid")}})
    out = []
    for f in queues.FRONTIERS:
        if component_id and f.component_id != component_id:
            continue
        reps = sorted(by.get(f.id, []), key=lambda x: x["process"])
        fresh = [x for x in reps if not x["stale"]]
        reason = None
        if not f.measured:
            reason = ("la librería no expone su ocupación: se declara el tope, no se inventa "
                      "la cifra")
        elif not reps:
            reason = "ningún proceso la ha informado en 24 h (proceso parado o aún sin desplegar)"
        elif not fresh:
            reason = f"sin informe en los últimos {STALE_S:.0f} s"
        out.append({
            "id": f.id, "component_id": f.component_id, "title_es": f.title_es,
            "why_es": f.why_es, "capacity": f.capacity, "unit": f.unit, "per_key": f.per_key,
            "policy": f.policy, "policy_es": queues.POLICY_ES[f.policy], "measured": f.measured,
            "processes": reps, "no_data": reason is not None, "no_data_reason": reason,
            "dropped": sum(x["dropped"] or 0 for x in reps) if reps else None,
            "max_occupancy": max((x["max_occupancy"] or 0 for x in reps), default=None)})
    return out


def register(r: APIRouter, store: ObsStore, envelope: Callable[..., dict[str, Any]]) -> None:
    @r.get("/queues")
    def queues_state(component_id: str | None = None) -> dict:
        if component_id is not None and len(component_id) > 80:
            raise HTTPException(400, "component_id demasiado largo")
        now = int(time.time() * 1000)
        items = frontiers_view(latest_reports(store, now), now, component_id)
        return envelope(items=items, total=len(items), report_every_s=queues.REPORT_EVERY_S,
                        keepalive_s=queues.KEEPALIVE_S, stale_s=STALE_S, window_ms=WINDOW_MS)
