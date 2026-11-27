"""Eventos del escáner al Observatorio por LOTES (T102), dentro del umbral de sobrecosto de T72.

Un barrido mira cientos de instrumentos; un evento por instrumento y paso superaría el tope de
`MAX_EVENTS_PER_CYCLE` (100) y el sobrecosto de `MAX_CYCLE_OVERHEAD_MS`. Por eso, tras publicar la
vista, se emite:

- **un resumen por clase y paso** (datos y agentes), con fuente y cobertura reales, que cubre a
  todos los instrumentos de la clase;
- **el recorrido completo de las candidatas más fuertes** (`TOP`, en el orden del ranking): dato →
  síntesis → proyección → decisión, con la traza determinista de su instrumento
  (`trace_for_instrument`), que es la misma que enseña el panel;
- el latido de la salud multiactivo y los cambios del despliegue gradual.

`event_key` hace deterministas los ids: republicar la misma pasada no duplica nada. Nunca lanza.
"""

from __future__ import annotations

import time
from collections.abc import Mapping

from eim.core.mode import Mode
from eim.observability.emit import emit
from eim.observability.events import Ref
from eim.observability.thresholds import MAX_CYCLE_OVERHEAD_MS, MAX_EVENTS_PER_CYCLE
from eim.scanner import health, rollout, trace

TOP = 5
_STATUS = {health.OK: "ok", health.DEGRADED: "degraded", health.STALE: "degraded",
           health.PAUSED: "degraded", health.NO_DATA: "no_data", health.ERROR: "error"}
SOURCE = "binance-futures (escáner global, T93)"


def _ev(kind: str, comp: str, key: str, **kw) -> dict:
    return {"kind": kind, "component_id": comp, "event_key": f"t102|{key}", **kw}


def _ordered(view: Mapping) -> list[tuple[dict, dict | None]]:
    rk = {r["opportunity_id"]: r for r in (view.get("ranking") or {}).get("rows") or []}
    opps = list(view.get("opportunities", []))
    opps.sort(key=lambda o: ((rk.get(o["opportunity_id"]) or {}).get("position") or 10**6,
                             -o["scores"]["signal_quality"]))
    return [(o, rk.get(o["opportunity_id"])) for o in opps]


def build(view: Mapping | None, h: Mapping, state: Mapping | None,
          changes: list[dict] | None = None, top: int = TOP) -> list[dict]:
    """Los eventos de una pasada (puro). Nunca más de `MAX_EVENTS_PER_CYCLE`."""
    out: list[dict] = []
    run = ((view or {}).get("deep") or {}).get("run_id") or f"salud-{h['generated_at']}"
    now = int(h["generated_at"])
    out.append(_ev("heartbeat", "scanner.health", f"{run}|salud|{now}", ts_utc=now,
                   status=_STATUS.get(h["overall"], "no_data"), run_id=run,
                   detail={"overall": h["overall"],
                           "classes": h["watching"]["classes"],
                           "instruments": h["watching"]["n_instruments"],
                           "view_age_h": h["view"]["age_h"]}))
    for ch in (changes or [])[:10]:
        out.append(_ev("alert", "scanner.rollout", f"{run}|{ch['unit']}|{ch['what']}|{now}",
                       ts_utc=now, run_id=run,
                       status="degraded" if ch["what"] in ("desactivada", "bajada") else "ok",
                       detail={"what": ch["what"], "unit": ch["unit"],
                                           "reason": ch["reason"][:180]}))
    if not view:
        return out
    tf = view["universe"]["timeframe"]
    pub = int(view.get("generated_at") or now)     # hechos de la pasada: misma hora, mismo id
    for c in h["classes"]:
        if not c["n_scored"]:
            continue
        cls = c["asset_class"]
        out.append(_ev("data_fetch", "scanner.service", f"{run}|datos|{cls}", run_id=run,
                       ts_utc=pub,
                       status=_STATUS.get(c["state"], "degraded"), source=SOURCE,
                       coverage=c["coverage"],
                       detail={"lote": "clase", "asset_class": cls, "n_scored": c["n_scored"],
                               "abiertos": c["markets"]["abierto"],
                               "cerrados": c["markets"]["cerrado"],
                               "stale_rows": c["stale_rows"], "quality_mean": c["quality_mean"],
                               "timeframe": tf}))
        out.append(_ev("synthesis", "scanner.deep", f"{run}|agentes|{cls}", run_id=run,
                       ts_utc=pub,
                       detail={"lote": "clase", "asset_class": cls,
                               "candidates": c["candidates"],
                               "above_threshold": c["above_threshold"]}))
    room = (MAX_EVENTS_PER_CYCLE - len(out)) // 4
    for opp, rk in _ordered(view)[:max(0, min(top, room))]:
        out.extend(_candidate(view, opp, rk, state, run, pub))
    return out[:MAX_EVENTS_PER_CYCLE]


def _candidate(view: Mapping, o: Mapping, rk: Mapping | None, state: Mapping | None,
               run: str, ts: int) -> list[dict]:
    iid, tid = o["instrument_id"], trace.trace_id_of(view, o["instrument_id"])
    ref = o.get("input_ref") or {}
    cand = Ref(type="candles", id=f"{o['symbol']}|{o['timeframe']}|{ref.get('cut')}"[:120],
               hash=(o.get("input_hash") or None))
    out_ref = Ref(type="opportunity", id=o["opportunity_id"])
    n = (o.get("coverage") or {}).get("n_bars")
    cov = None if not n else min(1.0, n / max(1, ref.get("n_bars") or n))
    syn = o.get("synthesis") or {}
    sc = (o.get("forecast") or {}).get("scenarios") or {}
    shadow = rollout.shadow_reason(o, state)
    above = bool((rk or {}).get("above_threshold"))
    base = {"run_id": run, "trace_id": tid, "ts_utc": ts}
    return [
        _ev("data_fetch", "scanner.service", f"{run}|{iid}|dato", source=o.get("source") or
            SOURCE, coverage=cov, outputs=(cand,), **base,
            detail={"instrument": iid, "asset_class": o["asset_class"], "n_bars": n}),
        _ev("synthesis", "scanner.deep", f"{run}|{iid}|sintesis", inputs=(cand,), **base,
            detail={"instrument": iid, "bias": syn.get("bias"),
                    "confidence": syn.get("confidence"), "agreement": syn.get("agreement"),
                    "agents": len(o.get("agents") or [])}),
        _ev("forecast", "scanner.deep", f"{run}|{iid}|proyeccion", inputs=(cand,), **base,
            detail={"instrument": iid, **{f"p_{k}": v.get("p") for k, v in sc.items()}}),
        _ev("plan", "scanner.rank", f"{run}|{iid}|decision", outputs=(out_ref,), **base,
            status="ok" if above and not shadow else "rejected",
            detail={"instrument": iid, "opportunity_id": o["opportunity_id"],
                    "side": o["side"], "priority": (rk or {}).get("priority"),
                    "above_threshold": above, "validated": False,
                    "decision": "candidata, no validada" + (" (en sombra)" if shadow else ""),
                    "level": rollout.level_of(o["asset_class"], state)["level"]}),
    ]


def emit_batch(events: list[dict]) -> dict:
    """Emite los eventos (nunca lanza) y mide su costo frente al umbral de T72."""
    t0 = time.perf_counter()
    sent = 0
    for e in events:
        kw = dict(e)
        sent += bool(emit(kw.pop("kind"), kw.pop("component_id"), mode=Mode.ANALISIS, **kw))
    ms = (time.perf_counter() - t0) * 1000
    return {"events": len(events), "queued": sent, "emit_ms": round(ms, 3),
            "limit_events": MAX_EVENTS_PER_CYCLE, "limit_ms": MAX_CYCLE_OVERHEAD_MS,
            "within": len(events) <= MAX_EVENTS_PER_CYCLE and ms <= MAX_CYCLE_OVERHEAD_MS}
