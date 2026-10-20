"""Rutas de trazabilidad del observatorio (T76): `/v2/obs/traces/{id}/explain` y `/v2/obs/quality`.

SOLO LECTURA. Marca y camino causal se calculan de los eventos indexados (`trace_view`,
`trace_text`); el `RiskDecision` completo, si existe, se lee del libro de riesgo sin copiarlo.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from eim.observability import thresholds as T
from eim.observability import trace_text as X
from eim.observability import trace_view as V
from eim.observability.store import ObsStore

_COLS = "event_id, trace_id, component_id, kind, status, coverage, detail, run_id, ts_utc"
_CHUNK = 200
_DAY = 86_400_000
_BUCKETS = {"hora": 3_600_000, "dia": _DAY}


def _events_by_trace(store: ObsStore, ids: list[str]) -> dict[str, list[dict]]:
    """Solo los eventos que pueden generar un hallazgo (estado distinto de ok o `data_fetch`);
    las trazas sin ningún evento crudo no aparecen como clave."""
    out: dict[str, list[dict]] = {}
    for i in range(0, len(ids), _CHUNK):
        part = ",".join("?" * len(ids[i:i + _CHUNK]))
        for r in store.query(f"SELECT DISTINCT trace_id FROM events WHERE trace_id IN ({part})",
                             ids[i:i + _CHUNK]):
            out[r["trace_id"]] = []
        for e in store.query(f"SELECT {_COLS} FROM events WHERE trace_id IN ({part}) AND "
                             "(status <> 'ok' OR kind = 'data_fetch') ORDER BY ts_utc",
                             ids[i:i + _CHUNK]):
            e["detail"] = json.loads(e["detail"]) if e["detail"] else {}
            out[e["trace_id"]].append(e)
    return out


def classify(store: ObsStore, decisions: list[dict]) -> list[dict]:
    """Marca de evidencia por traza. `mark` None = sin eventos crudos (ya purgados): no se sabe."""
    evs = _events_by_trace(store, [d["trace_id"] for d in decisions])
    crit = V.critical_agents()
    out = []
    for d in decisions:
        es = evs.get(d["trace_id"])
        found = V.findings(es, d.get("timeframe"), crit) if es else []
        out.append({"trace_id": d["trace_id"], "last_ms": d["last_ms"],
                    "mark": None if es is None else V.mark_of(found),
                    "causes": [(f["component_id"], f["cause"]) for f in found]})
    return out


def risk_row(conn: tuple[Any, threading.Lock] | None, events: list[dict]) -> dict | None:
    """`RiskDecision` completo del libro de riesgo (reglas con su cifra), si existe."""
    ev = next((e for e in events if e["kind"] == "risk_decision"), None)
    ref = next((o["id"] for o in (ev or {}).get("outputs", []) if o["type"] == "risk_decision"),
               None)
    if conn is None or not ref or "@" not in ref:
        return None
    plan_id, _, decided = ref.rpartition("@")
    if not decided.isdigit():
        return None
    con, lock = conn
    try:
        with lock:
            row = con.execute("SELECT decision FROM risk_decisions WHERE plan_id = ? AND "
                              "decided_at = ? LIMIT 1", [plan_id, int(decided)]).fetchone()
    except Exception:  # noqa: BLE001 - libro ausente en este equipo
        return None
    if not row:
        return None
    d = json.loads(row[0])
    return {"approved": d.get("approved"), "size": d.get("size"),
            "config_version": d.get("config_version"),
            "checks": [{"rule": c["rule"], "ok": c["ok"], "detail": c["detail"]}
                       for c in d.get("checks", [])]}


def register(r: APIRouter, store: ObsStore, envelope: Callable[..., dict],
             with_refs: Callable[[list[dict]], list[dict]],
             reports_conn: tuple[Any, threading.Lock] | None) -> None:
    @r.get("/traces/{trace_id}/explain")
    def explain(trace_id: str) -> dict:
        dec = store.query("SELECT * FROM decisions WHERE trace_id = ?", [trace_id])
        evs = store.query("SELECT * FROM events WHERE trace_id = ?", [trace_id])
        if not dec and not evs:
            raise HTTPException(404, f"sin traza {trace_id} (¿purgada o aún sin indexar?)")
        evs.sort(key=lambda e: (e["ts_utc"], e["kind"] != "run_start", e["event_id"]))
        evs = with_refs(evs)
        return envelope(trace_id=trace_id, partial=bool(dec) and not evs,
                        decision={k: dec[0][k] for k in ("symbol", "timeframe", "mode", "outcome",
                                                         "first_ms", "last_ms")} if dec else None,
                        **X.explain(evs, dec[0] if dec else None, risk_row(reports_conn, evs)))

    @r.get("/quality")
    def quality(desde: int | None = None, hasta: int | None = None, bucket: str = "dia",
                symbol: str | None = None, timeframe: str | None = None, mode: str | None = None,
                limit: int = Query(20_000, ge=1, le=50_000)) -> dict:
        if bucket not in _BUCKETS:
            raise HTTPException(400, "bucket debe ser 'hora' o 'dia'")
        now = int(time.time() * 1000)
        hasta = now if hasta is None else hasta
        desde = hasta - 7 * _DAY if desde is None else desde
        conds, args = ["last_ms >= ?", "last_ms < ?"], [desde, hasta]
        for col, val in (("symbol", symbol), ("timeframe", timeframe), ("mode", mode)):
            if val is not None:
                conds.append(f"{col} = ?")
                args.append(val)
        rows = store.query("SELECT trace_id, last_ms, timeframe FROM decisions WHERE "
                           + " AND ".join(conds) + f" ORDER BY last_ms LIMIT {int(limit)}", args)
        return envelope(
            **V.quality_report(classify(store, rows), desde, hasta, _BUCKETS[bucket]),
            bucket=bucket, marks_es=V.MARK_ES, stale_tf_factor=T.EVIDENCE_STALE_TF_FACTOR,
            critical_agents=list(V.critical_agents()),
            note_es="Solo informa: no excluye ni pondera nada de T47–T49.")
