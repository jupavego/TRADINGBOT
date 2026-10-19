"""Veredicto de una traza leída de `/v2/obs/traces/{id}` (T74). Puro: no abre red ni disco.

Lo usa `scripts/obs_verify_traces.py` (pasada con el proveedor real) y los tests. Cada
comprobación dice si es obligatoria; la cadena de órdenes solo se exige si el riesgo aprobó el
plan, y el riesgo solo si hubo plan: una vela sin plan o con plan vetado es un resultado
normal, no un fallo de la instrumentación.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from eim.observability import catalog


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def check_trace(events: list[dict], *, expected_agents: Iterable[str], mode: str,
                health_ok: bool = True) -> list[Check]:
    ev = events
    by_kind: dict[str, list[dict]] = {}
    for e in ev:
        by_kind.setdefault(e["kind"], []).append(e)
    out: list[Check] = [Check("indexador sano (/v2/obs/health)", health_ok, "")]

    fetch = [e for e in by_kind.get("data_fetch", []) if e["status"] in ("ok", "degraded")]
    seen = sorted({f"{e['source']} (cobertura {e['coverage']})" for e in fetch})
    out.append(Check("data_fetch declara su fuente",
                     bool(fetch) and all(e["source"] for e in fetch),
                     "; ".join(seen)[:200] or "ningún data_fetch"))
    want = {f"agent.{a}" for a in expected_agents}
    got = {e["component_id"] for e in by_kind.get("signal", [])}
    out.append(Check("una señal por agente", got == want,
                     f"{len(got)}/{len(want)}; faltan {sorted(want - got)}; "
                     f"sobran {sorted(got - want)}"))
    for kind in ("synthesis", "forecast", "plan"):
        out.append(Check(f"evento {kind}", bool(by_kind.get(kind)), ""))

    plan = next((e for e in by_kind.get("plan", [])), None)
    has_plan = plan is not None and plan["status"] == "ok"
    risk = [e for e in by_kind.get("risk_decision", []) if e["component_id"] == "risk.engine"]
    out.append(Check("risk_decision (si hay plan)", bool(risk) or not has_plan,
                     "con plan vigente" if has_plan else "sin plan vigente: no se evalúa",
                     required=has_plan))
    approved = any(e["status"] == "ok" for e in risk)
    for kind in ("order_intent", "order_sent", "fill"):
        out.append(Check(f"{kind} (si el riesgo aprobó)", bool(by_kind.get(kind)) or not approved,
                         "aprobado" if approved else "no aprobado: no se envía orden",
                         required=approved))

    starts = {e["run_id"] for e in by_kind.get("run_start", [])}
    ends = {e["run_id"] for e in by_kind.get("run_end", [])}
    out.append(Check("cada run_start tiene su run_end", starts == ends,
                     f"{len(starts)} tramos; sin cierre {sorted(starts - ends)[:3]}"))
    runs = {e["run_id"] for e in ev}
    outside = sorted({e["parent_run_id"] for e in ev
                      if e["parent_run_id"] and e["parent_run_id"] not in runs})
    # Los tramos de análisis cuelgan del tramo raíz del ciclo (o del difusor), que cubre varias
    # velas y no pertenece a una sola traza: un padre externo por origen es lo esperado; más es
    # un eslabón perdido.
    out.append(Check("sin eventos huérfanos", len(outside) <= 2,
                     f"{len(outside)} padre(s) fuera de la traza (tramo raíz del ciclo): "
                     f"{outside[:3]}" if outside else "todo padre está dentro de la traza"))
    unknown = sorted({e["component_id"] for e in ev if not catalog.has(e["component_id"])})
    out.append(Check("componentes dentro del catálogo", not unknown, str(unknown)))
    modes = {e["mode"] for e in ev}
    out.append(Check(f"modo {mode} en todos los eventos", modes == {mode}, str(sorted(modes))))
    return out


def render(checks: list[Check]) -> str:
    lines = []
    for c in checks:
        mark = "OK " if c.ok else ("FALLA" if c.required else "aviso")
        lines.append(f"[{mark:5}] {c.name}" + (f" — {c.detail}" if c.detail else ""))
    return "\n".join(lines)


def passed(checks: list[Check]) -> bool:
    return all(c.ok for c in checks if c.required)
