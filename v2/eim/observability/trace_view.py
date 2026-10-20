"""Calidad de la evidencia y camino causal de una traza (T76). Funciones PURAS sobre eventos ya
indexados (dicts como los devuelve `/v2/obs/traces/{id}`): sin I/O, sin LLM.

Todo motivo sale de lo que el sistema registró en el evento (`status`, `detail.error`, reglas
falladas, antigüedad del dato…); aquí no se inventa ni se redacta ninguna explicación libre.
Informa, no excluye: la marca no cambia nada en T47–T49.
"""

from __future__ import annotations

import re
from typing import Any

from eim.observability import thresholds as T

MARKS = ("limpia", "con_datos_obsoletos", "con_agente_critico_degradado", "con_error")
MARK_ES = {"limpia": "Limpia", "con_datos_obsoletos": "Con datos obsoletos",
           "con_agente_critico_degradado": "Con agente crítico degradado", "con_error": "Con error"}
# Causas que contaminan la evidencia → marca que provocan (prioridad: error > crítico > datos).
_CONTAMINATES = {"error": "con_error", "agente_critico_degradado": "con_agente_critico_degradado",
                 "dato_obsoleto": "con_datos_obsoletos", "cobertura_baja": "con_datos_obsoletos"}
_UNIT_MIN = {"m": 1, "h": 60, "d": 1440, "w": 10080}
_TF = re.compile(r"^(\d+)([mhdw])$")


def tf_minutes(tf: str | None) -> int | None:
    m = _TF.match((tf or "").strip().lower())
    return int(m.group(1)) * _UNIT_MIN[m.group(2)] if m else None


def critical_agents() -> tuple[str, ...]:
    """Agentes cuya falta invalida la decisión, según la configuración de riesgo vigente."""
    try:
        from eim.risk.config import load_config
        return tuple(load_config().critical_agents)
    except Exception:  # noqa: BLE001 - sin config legible no se supone nada
        return ()


def as_list(v: Any) -> list:
    if v is None or v == "":
        return []
    return v if isinstance(v, list) else [x.strip() for x in str(v).split(",") if x.strip()]


def why(e: dict, cause: str) -> str:
    d = e.get("detail") or {}
    if cause == "error":
        return str(d.get("error") or "; ".join(map(str, as_list(d.get("warnings")))) or
                   "falló sin mensaje registrado")
    if cause in ("dato_obsoleto", "cobertura_baja"):
        cov = e.get("coverage")
        return (f"dato de {d.get('key') or e['component_id']} con {d.get('age_min')} min de "
                "antigüedad" + (f" y cobertura {round(cov * 100)} %" if cov is not None else ""))
    if cause in ("agente_critico_degradado", "agente_degradado"):
        w = as_list(d.get("warnings"))
        return f"estado {e['status']}" + (f": {w[0]}" if w else "")
    if cause == "veto":
        rules, why = as_list(d.get("failed_rules")), as_list(d.get("reasons"))
        return ("; ".join(why) or "veto sin motivo registrado") + (
            f" (reglas: {', '.join(rules)})" if rules else "")
    if cause in ("sin_plan", "sin_sintesis"):
        return str(d.get("reason") or "sin motivo registrado")
    return f"estado {e['status']}"


def _cause(e: dict, tfm: int | None, crit: tuple[str, ...]) -> str | None:
    kind, st, d = e["kind"], e["status"], e.get("detail") or {}
    if st == "error":
        return "error"
    if kind == "data_fetch":
        age = d.get("age_min")
        if tfm and isinstance(age, int | float) and age > T.EVIDENCE_STALE_TF_FACTOR * tfm:
            return "dato_obsoleto"
        return "cobertura_baja" if st in ("degraded", "no_data") else None
    if kind == "signal" and st in ("degraded", "no_data"):
        return ("agente_critico_degradado" if e["component_id"].removeprefix("agent.") in crit
                else "agente_degradado")
    if kind == "risk_decision" and st == "rejected":
        return "veto"
    if kind == "plan" and st == "no_data":
        return "sin_plan"
    if kind == "synthesis" and st == "no_data":
        return "sin_sintesis"
    if kind in ("order_intent", "order_sent") and st == "rejected":
        return "orden_rechazada"
    return None


def findings(events: list[dict], timeframe: str | None = None,
             critical: tuple[str, ...] | None = None) -> list[dict]:
    """Hallazgos de una traza, uno por evento problemático, con su causa y su motivo registrado."""
    crit = critical_agents() if critical is None else critical
    tfm = tf_minutes(timeframe) or next(
        (tf_minutes((e.get("detail") or {}).get("timeframe")) for e in events
         if (e.get("detail") or {}).get("timeframe")), None)
    out: list[dict] = []
    for e in events:
        cause = _cause(e, tfm, crit)
        if cause:
            out.append({"event_id": e["event_id"], "component_id": e["component_id"],
                        "kind": e["kind"], "cause": cause, "why": why(e, cause),
                        "contaminates": cause in _CONTAMINATES, "ts_utc": e["ts_utc"]})
    return out


def mark_of(found: list[dict]) -> str:
    causes = {_CONTAMINATES[f["cause"]] for f in found if f["cause"] in _CONTAMINATES}
    return next((m for m in reversed(MARKS) if m in causes), "limpia")


def causal_path(events: list[dict], found: list[dict]) -> list[str]:
    """`event_id`s de la cadena hacia atrás: cada hallazgo más sus antecesores por
    `parent_run_id` (el eslabón que lo produjo)."""
    if not found:
        return []
    by_run: dict[str, list[dict]] = {}
    for e in events:
        by_run.setdefault(e["run_id"], []).append(e)
    chain = {f["event_id"] for f in found}
    for f in found:
        e = next(x for x in events if x["event_id"] == f["event_id"])
        seen: set[str] = set()
        parent = e.get("parent_run_id")
        while parent and parent not in seen:
            seen.add(parent)
            chain.update(x["event_id"] for x in by_run.get(parent, [])
                         if x["kind"] not in ("run_start", "run_end"))
            parent = (by_run.get(parent) or [{}])[0].get("parent_run_id")
    return [e["event_id"] for e in events if e["event_id"] in chain]


def quality_report(traces: list[dict], since: int, until: int, bucket_ms: int) -> dict:
    """Proporción de decisiones contaminadas. `traces`: [{trace_id, last_ms, mark|None, causes:
    [(componente, causa)]}]. Las trazas sin eventos crudos (purgados) no cuentan: se informan."""
    rows = [t for t in traces if t["mark"] is not None]
    dirty = [t for t in rows if t["mark"] != "limpia"]

    def share(n: int, d: int) -> float | None:
        return round(n / d, 4) if d else None

    periods: dict[int, list[dict]] = {}
    for t in rows:
        periods.setdefault(t["last_ms"] // bucket_ms * bucket_ms, []).append(t)
    by_comp: dict[str, set[str]] = {}
    by_cause: dict[str, set[str]] = {}
    for t in dirty:
        for comp, cause in t["causes"]:
            if cause in _CONTAMINATES:
                by_comp.setdefault(comp, set()).add(t["trace_id"])
                by_cause.setdefault(cause, set()).add(t["trace_id"])
    n = len(rows)
    return {
        "since": since, "until": until, "n_decisions": n, "n_dirty": len(dirty),
        "n_without_events": len(traces) - n, "dirty_share": share(len(dirty), n),
        "by_mark": {m: sum(1 for t in rows if t["mark"] == m) for m in MARKS},
        "by_period": [{"start_ms": k, "n": len(v), "dirty": sum(t["mark"] != "limpia" for t in v),
                       "dirty_share": share(sum(t["mark"] != "limpia" for t in v), len(v))}
                      for k, v in sorted(periods.items())],
        "by_component": sorted(({"component_id": c, "n": len(s), "share": share(len(s), n)}
                                for c, s in by_comp.items()), key=lambda x: -x["n"]),
        "by_cause": sorted(({"cause": c, "n": len(s), "share": share(len(s), n)}
                            for c, s in by_cause.items()), key=lambda x: -x["n"]),
    }
