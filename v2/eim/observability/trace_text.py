"""Relato y explicación de una traza (T76): español llano por PLANTILLAS sobre los campos
registrados (nunca un LLM, nunca un motivo que el sistema no haya anotado). Funciones puras.
"""

# ruff: noqa: E501  (plantillas de frases en español: se leen mejor en una línea)
from __future__ import annotations

from typing import Any

from eim.observability import catalog
from eim.observability import trace_view as V

_HEADLINE = {
    "ejecutada": "Hubo operación: la orden se ejecutó.",
    "orden_enviada": "Hubo operación: la orden se envió y aún no se rellena.",
    "orden_pedida": "Se pidió una orden, pero no consta que se enviara.",
    "aprobado": "El riesgo aprobó el plan, pero no se pidió ninguna orden.",
    "vetado": "No hubo operación: el riesgo vetó el plan.",
    "plan": "Hubo un plan, pero la decisión de riesgo no consta en la traza.",
    "sin_plan": "No hubo operación: el plan no encontró una operación clara.",
    "sintesis": "No hubo operación: no se llegó a un plan.",
    "senales": "No hubo operación: los agentes opinaron pero no hubo síntesis ni plan.",
    "datos": "No hubo operación: solo llegaron datos.",
}


def bias_word(b: Any) -> str:
    if not isinstance(b, int | float):
        return "sin sesgo registrado"
    if abs(b) < 0.1:
        return "neutral"
    return f"{'ligeramente ' if abs(b) < 0.4 else ''}{'alcista' if b > 0 else 'bajista'}"


def _n(x: Any, d: int = 2) -> str:
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",") if isinstance(x, int | float) else "—"


def _age(m: Any) -> str:
    if not isinstance(m, int | float):
        return "sin antigüedad registrada"
    return "recién" if m < 1 else f"hace {_n(m, 0)} min" if m < 120 else f"hace {_n(m / 60, 1)} h"


def title(component_id: str) -> str:
    c = catalog.get(component_id)
    return c.title_es if c else component_id


def step_text(e: dict) -> str:
    """Una frase por evento, con las cifras tal como se registraron."""
    d, who, st = e.get("detail") or {}, title(e["component_id"]), e["status"]
    k = e["kind"]
    if k == "data_fetch":
        cov = e.get("coverage")
        return (f"{who} entregó {d.get('key') or 'datos'} de {e.get('source') or 'fuente no declarada'} "
                f"({_age(d.get('age_min'))}, "
                f"{'sin huecos' if cov == 1 else 'cobertura ' + _n(cov * 100, 0) + ' %' if cov is not None else 'cobertura sin registrar'})"
                f"{'; es dato viejo' if st == 'degraded' else ''}.")
    if k == "signal":
        if st == "error":
            return f"{who} falló ({d.get('error') or 'sin mensaje'}); el ciclo siguió sin su opinión."
        if st == "no_data":
            return f"{who} no tuvo datos suficientes y no opinó."
        tail = " Con datos incompletos." if st == "degraded" else ""
        warn = as_first(d.get("warnings"))
        return (f"{who} opinó: {bias_word(d.get('bias'))}, confianza {_n(d.get('confidence'))}."
                f"{tail}{' Advertencia: ' + warn + '.' if warn else ''}")
    if k == "synthesis":
        if st == "no_data":
            return f"{who} no pudo juntar opiniones ({d.get('reason') or 'sin motivo registrado'})."
        return (f"{who} reunió {d.get('voters', '—')} opiniones: {bias_word(d.get('bias'))}, "
                f"confianza {_n(d.get('confidence'))}, acuerdo entre agentes {_n(d.get('agreement'))}.")
    if k == "forecast":
        return (f"{who} proyectó 3 escenarios a {d.get('horizon_bars', '—')} velas "
                f"({d.get('engine') or 'motor sin nombre'}).")
    if k == "plan":
        if st == "no_data":
            return f"No hubo plan: {d.get('reason') or 'sin motivo registrado'}."
        return (f"El plan propuso una operación {_side(d.get('side'))} con entrada {_n(d.get('entry'))}, "
                f"SL {_n(d.get('sl'))} y relación riesgo/beneficio {_n(d.get('rr'))}.")
    if k == "risk_decision":
        if st == "rejected":
            return f"El riesgo vetó: {V.why(e, 'veto')}."
        return (f"El riesgo aprobó el plan con tamaño {_n(d.get('size'), 4)} y apalancamiento "
                f"{_n(d.get('leverage'))}x.")
    if k == "order_intent":
        return f"{who} pidió una orden {_side(d.get('side'))}." if st != "rejected" \
            else f"{who} no pudo pedir la orden."
    if k == "order_sent":
        return (f"{who} envió la orden." if st == "ok" else f"{who} no pudo enviar la orden "
                f"({d.get('error') or st}).")
    if k == "fill":
        return f"{who}: {d.get('what') or 'relleno'} de {_n(d.get('qty'), 4)} a {_n(d.get('price'))}."
    return f"{who}: evento {k} con estado {st}."


def as_first(v: Any) -> str:
    items = V.as_list(v)
    return str(items[0]) if items else ""


def _side(s: Any) -> str:
    return "larga" if s in (1, "1", "long", "LONG") else "corta" if s in (-1, "-1", "short") else ""


def build_steps(events: list[dict], causal: set[str], found: dict[str, dict]) -> list[dict]:
    """Pasos numerados (sin `run_start/run_end`): qué consumió, qué produjo y su frase."""
    out: list[dict] = []
    for e in (x for x in events if x["kind"] not in ("run_start", "run_end")):
        d = e.get("detail") or {}
        out.append({
            "n": len(out) + 1, "event_id": e["event_id"], "component_id": e["component_id"],
            "title_es": title(e["component_id"]), "kind": e["kind"], "status": e["status"],
            "ts_utc": e["ts_utc"], "duration_ms": e.get("duration_ms"), "run_id": e["run_id"],
            "text_es": step_text(e), "causal": e["event_id"] in causal,
            "finding": found.get(e["event_id"]),
            "consumed": {"source": e.get("source"), "age_min": d.get("age_min"),
                         "coverage": e.get("coverage"), "refs": e.get("inputs", [])},
            "produced": {k: d[k] for k in ("bias", "confidence", "agreement", "side", "size",
                                           "approved") if k in d} | {
                "warnings": V.as_list(d.get("warnings")), "refs": e.get("outputs", []),
                "params_version": next((r.get("params_version") for r in e.get("outputs", [])
                                        if r.get("params_version")), None)},
        })
    return out


def agents_panel(steps: list[dict], events: list[dict]) -> list[dict]:
    """Sesgo de cada agente frente a la síntesis (desacuerdo = diferencia registrada)."""
    syn = next((e for e in events if e["kind"] == "synthesis" and e["status"] == "ok"), None)
    sb = ((syn or {}).get("detail") or {}).get("bias")
    rows = []
    for s in steps:
        if s["kind"] != "signal":
            continue
        b = s["produced"].get("bias")
        diff = round(b - sb, 4) if isinstance(b, int | float) and isinstance(sb, int | float) else None
        rows.append({"component_id": s["component_id"], "title_es": s["title_es"],
                     "status": s["status"], "bias": b, "confidence": s["produced"].get("confidence"),
                     "vs_synthesis": diff,
                     "opposes": bool(diff is not None and b is not None and abs(b) >= 0.1
                                     and sb is not None and abs(sb) >= 0.1 and (b > 0) != (sb > 0)),
                     "warnings": s["produced"]["warnings"]})
    return rows


def risk_panel(events: list[dict], decision_row: dict | None) -> dict | None:
    """Reglas de riesgo: del `RiskDecision` registrado si existe (cifras reales); si no, solo
    lo que anotó el evento (reglas falladas y motivos)."""
    e = next((x for x in events if x["kind"] == "risk_decision"), None)
    if e is None:
        return None
    d = e.get("detail") or {}
    base = {"approved": e["status"] != "rejected", "size": d.get("size"),
            "leverage": d.get("leverage"), "reasons": V.as_list(d.get("reasons")),
            "failed_rules": V.as_list(d.get("failed_rules")),
            "config_version": next((r.get("params_version") for r in e.get("outputs", [])
                                    if r.get("params_version")), None)}
    if decision_row:
        return base | {"source": "risk_decisions (RiskDecision completo)",
                       "checks": decision_row.get("checks", []),
                       "approved": decision_row.get("approved", base["approved"]),
                       "size": decision_row.get("size", base["size"]),
                       "config_version": decision_row.get("config_version") or base["config_version"]}
    return base | {"source": "evento risk_decision (sin el RiskDecision completo)", "checks": []}


def order_fact(events: list[dict]) -> dict:
    last = None
    for k, name in (("order_intent", "pedida"), ("order_sent", "enviada"), ("fill", "ejecutada")):
        for e in events:
            if e["kind"] == k:
                last = {"state": name if e["status"] != "error" else "con_error", "status":
                        e["status"], "component_id": e["component_id"], "ts_utc": e["ts_utc"]}
    return last or {"state": "sin_orden", "status": None, "component_id": None, "ts_utc": None}


def explain(events: list[dict], decision: dict | None, decision_row: dict | None = None) -> dict:
    """`/explain`: marca, hallazgos, camino causal, relato y los tres hechos por separado."""
    tf = (decision or {}).get("timeframe")
    found = V.findings(events, tf)
    chain = V.causal_path(events, found)
    by_id = {f["event_id"]: f for f in found}
    steps = build_steps(events, set(chain), by_id)
    outcome = (decision or {}).get("outcome") or "datos"
    syn = next((e for e in events if e["kind"] == "synthesis"), None)
    sd = (syn or {}).get("detail") or {}
    return {
        "mark": V.mark_of(found), "mark_es": V.MARK_ES[V.mark_of(found)], "outcome": outcome,
        "headline_es": _HEADLINE.get(outcome, "Resultado sin clasificar."),
        "findings": found, "causal_path": chain, "steps": steps,
        "reasons_es": [f"{title(f['component_id'])}: {f['why']}" for f in found],
        "facts": {
            "signal": {"bias": sd.get("bias"), "confidence": sd.get("confidence"),
                       "agreement": sd.get("agreement"), "status": (syn or {}).get("status"),
                       "text_es": step_text(syn) if syn else "Sin síntesis en la traza."},
            "decision": {"state": ("sin_decision" if not (decision or {}).get("risk_event")
                                   else "vetada" if (decision or {}).get("risk_status") == "rejected"
                                   else "aprobada"), "risk": risk_panel(events, decision_row)},
            "order": order_fact(events)},
        "agents": agents_panel(steps, events),
    }
