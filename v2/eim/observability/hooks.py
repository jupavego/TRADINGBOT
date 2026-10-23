"""Ganchos de la cadena de decisión (T74): de la vela cerrada a la orden.

Funciones pequeñas que los puntos de instrumentación (corredor, ciclo, motor de riesgo, puerta
de órdenes) llaman en una línea. Ninguna lanza: un fallo de observabilidad se traga, nunca
altera lo observado. Los eventos de la cadena (`signal`, `synthesis`, `forecast`, `plan`,
`risk_decision`…) comparten el `trace_id` de la vela (`trace_for(símbolo, marco, cierre)`).

Regla de volumen: los eventos de análisis solo se emiten dentro de una traza abierta (ciclo
de operación o difusor de la API); backtests, calibraciones y consultas de la UI llaman al
mismo código y no producen nada. Los servicios en segundo plano están en `hooks_service.py`.
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from eim.core import AgentReport, Mode
from eim.observability import emit as _emit_mod
from eim.observability.emit import emit
from eim.observability.events import Ref, new_run_id, proposal_trace, trace_for

_REMEMBER_MAX = 128
_links: OrderedDict[str, str] = OrderedDict()
_links_lock = threading.Lock()


def safe(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Un gancho nunca lanza: si falla, no pasa nada."""
    @functools.wraps(fn)
    def wrapper(*a: Any, **kw: Any) -> Any:
        try:
            return fn(*a, **kw)
        except Exception:  # noqa: BLE001 - observar no puede romper lo observado
            return None
    return wrapper


def enabled() -> bool:
    try:
        return _emit_mod._em().enabled
    except Exception:  # noqa: BLE001
        return False


def current_trace() -> str | None:
    cur = _emit_mod.current()
    return cur[1] if cur else None


def traced_span(component_id: str, **kw: Any) -> Any:
    """`span` solo dentro de una traza abierta; fuera (backfills, backtests) no hace nada."""
    if enabled() and current_trace() is not None:
        return _emit_mod.span(component_id, **kw)
    return contextlib.nullcontext()


def remember(key: str, run_id: str) -> None:
    """Guarda el `run_id` de un eslabón para que el siguiente lo use como `parent_run_id`."""
    with _links_lock:
        _links[key] = run_id
        while len(_links) > _REMEMBER_MAX:
            _links.popitem(last=False)


def recall(key: str) -> str | None:
    with _links_lock:
        return _links.get(key)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot_ref(snap: Any) -> Ref:
    """Huella de entrada del snapshot: velas, funding, fuentes y cobertura (no el volcado)."""
    cs = snap.candles
    body = repr((snap.symbol, snap.timeframe, snap.asof,
                 tuple((c.t, c.o, c.h, c.l, c.c, c.v) for c in cs),
                 tuple(snap.funding or ()), sorted(snap.sources.items()),
                 sorted(snap.coverage.items())))
    return Ref(type="snapshot", id=f"{snap.symbol}:{snap.timeframe}:{snap.asof}", hash=_sha(body))


def report_ref(r: AgentReport) -> Ref:
    return Ref(type="agent_report", id=f"{r.agent_id}:{r.asof}", hash=_sha(r.model_dump_json()),
               params_version=r.version)


@dataclass
class AgentRunCtx:
    """Estado de una pasada del corredor: huella de entrada y qué agente corrió en qué tramo."""

    snap_ref: Ref
    trace_id: str | None
    runs: dict[str, str] = field(default_factory=dict)       # agent_id → run_id del tramo
    timed_out: set[str] = field(default_factory=set)


@safe
def begin_agents(snap: Any) -> AgentRunCtx | None:
    """None si no hay observabilidad o no hay traza abierta (el corredor no hace nada más)."""
    if not enabled() or current_trace() is None:
        return None
    return AgentRunCtx(snapshot_ref(snap), current_trace())


def _state(r: AgentReport, failed: bool) -> str:
    return "error" if failed else r.status


@safe
def agent_signal(ctx: AgentRunCtx, r: AgentReport, *, failed: bool = False,
                 run_id: str | None = None) -> None:
    """Un `signal` por agente: sesgo, confianza, estado y referencias de entrada y salida."""
    if r.agent_id in ctx.timed_out:        # el hilo terminó tarde: ya se registró el timeout
        return
    emit("signal", f"agent.{r.agent_id}", status=_state(r, failed),  # type: ignore[arg-type]
         run_id=run_id, trace_id=ctx.trace_id, inputs=[ctx.snap_ref], outputs=[report_ref(r)],
         detail={"bias": round(r.bias, 4), "confidence": round(r.confidence, 4),
                 "horizon_bars": r.horizon_bars, "status": r.status,
                 "warnings": [w[:120] for w in r.warnings[:3]]})


@safe
def agent_timeout(ctx: AgentRunCtx, agent: Any, r: AgentReport, limit_s: float) -> None:
    ctx.timed_out.add(agent.id)
    emit("signal", f"agent.{agent.id}", status="error", run_id=new_run_id(),
         trace_id=ctx.trace_id, inputs=[ctx.snap_ref], outputs=[report_ref(r)],
         detail={"bias": 0.0, "confidence": 0.0, "status": r.status,
                 "error": f"timeout tras {limit_s:g}s"})


@safe
def after_agents(ctx: AgentRunCtx, reports: list[AgentReport], expected: list[str]) -> None:
    """Síntesis (misma llamada que ve la UI) y plan vigente, tras terminar todos los agentes."""
    from eim.synthesis import synthesize
    syn = synthesize(reports, expected=expected)
    plan_rep = next((r for r in reports if r.agent_id == "plan"), None)
    plan_run = ctx.runs.get("plan")
    emit("synthesis", "synthesis.thesis", status="ok" if syn else "no_data",
         run_id=new_run_id(), trace_id=ctx.trace_id, inputs=[report_ref(r) for r in reports][:16],
         detail=({"bias": round(syn.bias, 4), "confidence": round(syn.confidence, 4),
                  "agreement": round(syn.agreement, 4), "voters": len(syn.weights)}
                 if syn else {"reason": "ningún agente aporta"}))
    if plan_rep is None:
        return
    plan = plan_rep.metrics.get("plan") or None
    pid = plan_rep.overlays[0].id if plan and plan_rep.overlays else f"plan:{plan_rep.asof}"
    rid = new_run_id()
    emit("plan", "agent.plan", status="ok" if plan else "no_data", run_id=rid,
         parent_run_id=plan_run, trace_id=ctx.trace_id, inputs=[report_ref(plan_rep)],
         outputs=[Ref(type="plan", id=pid)] if plan else [],
         detail=({k: plan.get(k) for k in ("side", "entry", "sl", "rr", "status")}
                 if plan else {"reason": (plan_rep.evidence or ["sin plan vigente"])[0]}))
    if plan:
        remember(f"plan:{pid}", rid)


@safe
def snapshot_fetches(snap: Any, wanted: int) -> None:
    """Un `data_fetch` por fuente del snapshot: fuente declarada, cobertura real y antigüedad."""
    if current_trace() is None or not snap.candles:
        return
    c_lo, c_hi = snap.coverage.get("candles", (snap.candles[0].t, snap.candles[-1].t))
    for key, source in snap.sources.items():
        lo, hi = snap.coverage.get(key, (None, None))
        if key == "candles":
            cov: float | None = min(1.0, len(snap.candles) / wanted) if wanted else None
        elif lo is not None and hi is not None and hi > lo and c_hi > c_lo:
            cov = min(1.0, (hi - lo) / (c_hi - c_lo))
        else:
            cov = None
        emit("data_fetch", _component_for(key), run_id=new_run_id(), source=source[:120],
             coverage=cov, status="ok" if cov is None or cov >= 0.5 else "degraded",
             detail={"key": key, "age_min": round((snap.asof - hi) / 60_000) if hi else None})


def _component_for(key: str) -> str:
    base = key.split(":")[0]
    if base == "micro" or base == "orderbook":
        return "data.micro_collector"
    if base == "events":
        return "data.calendar"
    if base == "arb":
        return "data.arb_market"
    if base == "leaders":
        return "leaders.service"
    return "data.store"


@safe
def forecast_done(fs: Any) -> None:
    if current_trace() is None:
        return
    probs = {s.id: round(s.probability, 4) for s in fs.scenarios}
    emit("forecast", "forecast.engine", run_id=new_run_id(),
         outputs=[Ref(type="forecast_set", id=f"{fs.symbol}:{fs.timeframe}:{fs.made_at}")],
         detail={**probs, "horizon_bars": fs.horizon_bars, "engine": fs.engine,
                 "warnings": [w[:120] for w in fs.warnings[:3]]})


def _trace_of(d: Any) -> str:
    p = getattr(d, "proposal", None)
    return proposal_trace(p) if p is not None else trace_for(d.symbol, d.timeframe, d.asof)


def proposal_refs(p: Any) -> list[Ref]:
    """Datos usados por una decisión (T114): la propuesta (huella y versión de la fuente) y el
    dato hasta el que se decidió. Referencias, nunca volcados."""
    return [Ref(type="proposal", id=p.proposal_id[:120], hash=_sha(p.model_dump_json())[:16],
                params_version=p.source_version[:60]),
            Ref(type="data", id=f"{p.symbol}:{p.timeframe}:{p.data_asof}"[:120])]


def decision_detail(d: Any) -> dict[str, Any]:
    """Lo que el Observatorio guarda de una decisión: resultado, autoridad, fuente y salida."""
    p = getattr(d, "proposal", None)
    return {"approved": d.approved, "result": "aprobada" if d.approved else "rechazada",
            "side": d.side, "size": d.size, "leverage": d.leverage,
            "failed_rules": [c.rule for c in d.checks if not c.ok],
            "reasons": [r[:120] for r in d.reasons[:4]],
            "authority": getattr(d, "authority", "risk.engine"),
            "source": p.source if p else None, "source_version": p.source_version if p else None,
            "symbol": d.symbol, "timeframe": d.timeframe,
            "exit_mode": getattr(d, "exit_mode", None),
            "profile_version": getattr(d, "profile_version", None),
            "expires_at": p.expires_at if p else None}


@safe
def risk_decided(d: Any, *, always: bool = False, key: str | None = None,
                 ts: int | None = None, trace_id: str | None = None) -> None:
    """`risk_decision`: id y sello de la decisión, reglas que fallaron. Dentro de una traza se
    registra siempre; fuera (consulta de la UI) solo si se aprobó, para no inundar (`always`
    lo fuerza: decisiones del bróker en vivo). T114: el componente es la autoridad que decidió y
    el detalle dice la fuente, su versión, los datos usados y el resultado; `key` hace el
    `event_id` determinista (reemitir no duplica) y `ts` lo fecha al instante de la decisión."""
    if current_trace() is None and not d.approved and not always:
        return
    rid = new_run_id()
    p = getattr(d, "proposal", None)
    tid = trace_id or _trace_of(d)
    emit("risk_decision", getattr(d, "authority", "risk.engine"),
         status="ok" if d.approved else "rejected", run_id=rid,
         parent_run_id=recall(f"plan:{d.plan_id}"), trace_id=tid, mode=d.mode,
         inputs=[Ref(type="plan", id=d.plan_id[:120]), *(proposal_refs(p) if p else [])],
         outputs=[Ref(type="risk_decision", id=f"{d.plan_id}@{d.decided_at}"[:120],
                      hash=(d.seal or "")[:16] or None, params_version=d.config_version)],
         detail=decision_detail(d), ts_utc=ts, event_key=key)
    remember(f"risk:{d.plan_id}", rid)
    remember(f"trace:{d.plan_id}", tid)


@safe
def order_event(kind: str, component: str, plan_id: str, *, mode: Mode, status: str = "ok",
                detail: dict | None = None, key: str | None = None) -> None:
    """`order_intent` / `order_sent` / `fill` (y `alert` si el envío falla): eventos distintos
    entre sí y de la señal y la decisión.
    La traza y el eslabón anterior se recuperan por `plan_id` (lo dejó `risk_decided`)."""
    chain = {"order_intent": "risk", "order_sent": "order_intent", "fill": "order_sent",
             "alert": "order_sent"}[kind]
    rid = new_run_id()
    emit(kind, component, status=status, run_id=rid,  # type: ignore[arg-type]
         parent_run_id=recall(f"{chain}:{plan_id}"), trace_id=recall(f"trace:{plan_id}"),
         mode=mode, inputs=[Ref(type="plan", id=plan_id)],
         outputs=[Ref(type="order", id=key)] if key else [], detail=detail or {})
    remember(f"{kind}:{plan_id}", rid)


@safe
def fill_event(plan_id: str, mode: Mode, key: str, what: str, qty: float,
               price: float | None) -> None:
    """Relleno en el broker (entrada, SL/TP o cierre ordenado) del libro SIMULADO o la testnet."""
    comp = "execution.sim_broker" if mode is Mode.SIMULADO else "execution.testnet_broker"
    order_event("fill", comp, plan_id, mode=mode, key=key,
                detail={"what": what, "qty": qty, "price": price})
