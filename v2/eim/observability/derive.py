"""Derivados del indexador (T73): `runs` y `decisions` plegados evento a evento.

Solo se pliegan eventos NUEVOS (los repetidos ya se descartaron por `event_id`), así que un
re-índice no duplica contadores. El pliegue se hace sobre la fila ya guardada: al purgar los
eventos crudos viejos, `runs` y `decisions` conservan lo aprendido.
"""

from __future__ import annotations

import json
from typing import Any

from eim.observability import catalog
from eim.observability.events import ObsEvent

LINK_TYPES = ("agent_report", "plan", "risk_decision", "sim_trade", "order")
MAX_LINKS = 50
_STAGE_FIELD = {"synthesis": "synthesis_event", "forecast": "forecast_event",
                "plan": "plan_event", "risk_decision": "risk_event",
                "order_intent": "order_event", "order_sent": "sent_event", "fill": "fill_event"}


def _code_version(ev: ObsEvent) -> str | None:
    v = ev.detail.get("code_version")
    if v:
        return str(v)
    comp = catalog.get(ev.component_id)
    return comp.version if comp else None


def _params_version(ev: ObsEvent) -> str | None:
    v = ev.detail.get("params_version")
    if v:
        return str(v)
    return next((r.params_version for r in (*ev.inputs, *ev.outputs) if r.params_version), None)


def fold_run(row: dict[str, Any] | None, ev: ObsEvent) -> dict[str, Any] | None:
    """`run_start`/`run_end` → fila de `runs` (en cualquier orden de llegada). Otros → None."""
    if ev.kind not in ("run_start", "run_end"):
        return row
    r = dict(row) if row else {
        "run_id": ev.run_id, "component_id": ev.component_id, "process": ev.process,
        "trace_id": ev.trace_id, "parent_run_id": ev.parent_run_id, "started_ms": None,
        "ended_ms": None, "status": "running", "duration_ms": None, "mode": ev.mode.value,
        "code_version": None, "params_version": None, "error": None}
    r["trace_id"] = r["trace_id"] or ev.trace_id
    r["parent_run_id"] = r["parent_run_id"] or ev.parent_run_id
    r["code_version"] = r["code_version"] or _code_version(ev)
    r["params_version"] = r["params_version"] or _params_version(ev)
    if ev.kind == "run_start":
        r["started_ms"] = ev.ts_utc
    else:
        r["ended_ms"], r["status"], r["duration_ms"] = ev.ts_utc, ev.status, ev.duration_ms
        err = ev.detail.get("error")
        if err and ev.status in ("error", "degraded", "rejected"):
            r["error"] = str(err)
    if r["started_ms"] is not None and r["ended_ms"] is not None and r["duration_ms"] is None:
        r["duration_ms"] = float(r["ended_ms"] - r["started_ms"])
    return r


def _outcome(d: dict[str, Any]) -> str:
    if d["fill_event"]:
        return "ejecutada"
    if d["sent_event"]:
        return "orden_enviada"
    if d["risk_status"] == "rejected":
        return "vetado"
    if d["order_event"]:
        return "orden_pedida"
    if d["risk_event"]:
        return "aprobado"
    if d["plan_event"]:
        return "plan"
    if "sin_plan" in json.loads(d["links"] or "{}"):      # T76: el plan dijo «no hay operación»
        return "sin_plan"
    if d["synthesis_event"] or d["forecast_event"]:
        return "sintesis"
    return "senales" if d["n_signals"] else "datos"


def fold_decision(row: dict[str, Any] | None, ev: ObsEvent) -> dict[str, Any] | None:
    """Eventos con traza → fila de `decisions` (señales → síntesis → plan → riesgo → orden)."""
    if not ev.trace_id:
        return row
    d = dict(row) if row else {
        "trace_id": ev.trace_id, "symbol": None, "timeframe": None, "mode": ev.mode.value,
        "first_ms": ev.ts_utc, "last_ms": ev.ts_utc, "n_events": 0, "n_signals": 0,
        "synthesis_event": None, "forecast_event": None, "plan_event": None,
        "risk_event": None, "risk_status": None, "order_event": None, "sent_event": None,
        "fill_event": None, "outcome": "datos", "has_error": False, "links": "{}"}
    d["n_events"] += 1
    d["first_ms"], d["last_ms"] = min(d["first_ms"], ev.ts_utc), max(d["last_ms"], ev.ts_utc)
    d["symbol"] = d["symbol"] or ev.detail.get("symbol")
    d["timeframe"] = d["timeframe"] or ev.detail.get("timeframe")
    d["has_error"] = bool(d["has_error"]) or ev.status == "error"
    if ev.kind == "signal":
        d["n_signals"] += 1
    field = _STAGE_FIELD.get(ev.kind)
    links = json.loads(d["links"] or "{}")
    if ev.kind == "plan" and ev.status == "no_data":     # T76: no es un plan, se anota aparte
        links.setdefault("sin_plan", [ev.event_id])
        field = None
    if field and not d[field]:
        d[field] = ev.event_id
    if ev.kind == "risk_decision" and d["risk_status"] != "rejected":  # un veto no se revierte
        d["risk_status"] = ev.status
    for ref in (*ev.inputs, *ev.outputs):
        if ref.type in LINK_TYPES:
            lst = links.setdefault(ref.type, [])
            if ref.id not in lst and len(lst) < MAX_LINKS:
                lst.append(ref.id)
    d["links"] = json.dumps(links, sort_keys=True)
    d["outcome"] = _outcome(d)
    return d


def stage_rank(component_id: str) -> int:
    """Orden de la etapa del componente (desempata eventos con el mismo instante)."""
    comp = catalog.get(component_id)
    return catalog.STAGES.index(comp.stage) if comp else len(catalog.STAGES)
