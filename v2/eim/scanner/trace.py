"""Recorrido de una candidata, de su dato a su decisión (T102). Puro, sobre la vista publicada.

Responde «¿de dónde salió esto y qué se decidió?» para un instrumento del último barrido, en ocho
pasos con su estado y sus cifras: el dato de origen (fuente, nivel, licencia, velas exactas y su
huella), el embudo, los agentes que corrieron y los que no (con su motivo), la síntesis, la
proyección, la oportunidad, el ranking contra el azar y la **decisión**: siempre «candidata, no
validada», visible o en sombra según el despliegue gradual, con lo que le falta para subir.

La traza (`trace_id`) es la misma que llevan los eventos del observatorio de ese instrumento en esa
vela (`trace_for_instrument`), así que el recorrido del panel y el del mapa coinciden.
"""

from __future__ import annotations

from collections.abc import Mapping

from eim.data.providers.meta import lookup
from eim.data.timeframes import tf_ms, tf_offset
from eim.observability.events import trace_for_instrument
from eim.scanner import rollout
from eim.scanner.universe import closed_cut

TRACE_VERSION = "1"
_ST = {"ok": "ok", "degraded": "degradado", "no_data": "sin_datos"}


def cut_of(view: Mapping) -> int:
    u = view["universe"]
    tf = u["timeframe"]
    return closed_cut(tf_ms(tf), int(u["asof"]), tf_offset(tf))


def trace_id_of(view: Mapping, instrument_id: str) -> str:
    return trace_for_instrument(instrument_id, view["universe"]["timeframe"], cut_of(view))


def _step(key: str, title: str, status: str, summary: str, **detail) -> dict:
    return {"key": key, "title": title, "status": status, "summary": summary, "detail": detail}


def _data_step(row: Mapping | None, opp: Mapping | None, deep: Mapping | None) -> dict:
    src = (opp or {}).get("source") or "binance-futures (escáner global, T93)"
    meta = lookup(src)
    ref = (opp or {}).get("input_ref") or {}
    q = (row or {}).get("quality")
    status = "ok" if q is not None and q >= 1.0 else "degradado" if row else "sin_datos"
    n = ref.get("n_bars") or ((deep or {}).get("coverage") or {}).get("n_bars")
    return _step("dato", "Dato de origen", status,
                 f"{n or '—'} velas de {src} (nivel {meta.coverage}); calidad "
                 f"{'—' if q is None else f'{q:.2f}'}; mercado {(row or {}).get('state', '—')}",
                 source=src, level=meta.coverage, license=meta.license,
                 input_hash=(opp or deep or {}).get("input_hash"), input_ref=ref,
                 last_t=(row or {}).get("last_t"), quality=q,
                 market_state=(row or {}).get("state"))


def _agents_step(deep: Mapping) -> dict:
    ran, skipped = deep.get("ran") or [], deep.get("skipped") or []
    bad = [r["agent_id"] for r in ran if r["status"] != "ok"]
    return _step("agentes", "Agentes", "degradado" if bad else "ok",
                 f"{len(ran)} corrieron ({len(bad)} degradados), {len(skipped)} no pudieron "
                 "opinar", ran=[{"agent_id": r["agent_id"], "version": r["version"],
                                 "status": _ST.get(r["status"], r["status"]),
                                 "bias": r["bias"], "confidence": r["confidence"]} for r in ran],
                 skipped=[{"agent_id": s["agent_id"], "reason": s["reason"]} for s in skipped])


def _rank_step(k: Mapping | None) -> dict:
    if not k:
        return _step("ranking", "Ranking contra el azar", "sin_datos",
                     "sin ranking en esta pasada")
    m = k.get("multiplicity") or {}
    above = bool(k.get("above_threshold"))
    return _step("ranking", "Ranking contra el azar", "ok" if above else "degradado",
                 f"puesto {k.get('position') or '—'}, prioridad "
                 f"{'—' if k.get('priority') is None else round(k['priority'], 3)} "
                 f"({'sobre' if above else 'bajo'} el umbral del azar); p de Holm "
                 f"{m.get('p_holm', '—')} en una familia de {m.get('n_family', '—')}",
                 priority=k.get("priority"), position=k.get("position"), above_threshold=above,
                 cluster_id=k.get("cluster_id"), representative=k.get("representative"),
                 multiplicity=m)


def candidate_trace(view: Mapping | None, instrument_id: str,
                    state: Mapping | None = None) -> dict | None:
    """El recorrido de `instrument_id` en la última vista; None si no está en ella."""
    if not view:
        return None
    row = next((r for r in view["universe"]["rows"] if r["instrument_id"] == instrument_id),
               None)
    deep = view.get("instruments", {}).get(instrument_id)
    if row is None and deep is None:
        return None
    opp = next((o for o in view.get("opportunities", [])
                if o["instrument_id"] == instrument_id), None)
    rk = next((r for r in (view.get("ranking") or {}).get("rows") or []
               if opp and r["opportunity_id"] == opp["opportunity_id"]), None)
    cls = (row or deep or {}).get("asset_class") or instrument_id.split(".", 1)[0]
    steps = [_data_step(row, opp, deep)]
    steps.append(_step("embudo", "Embudo del escáner", "ok" if (row or {}).get("deep") else
                       "degradado",
                       f"puesto {(row or {}).get('rank', '—')} de "
                       f"{view['universe'].get('n_scored', '—')} por interés; "
                       + ("entra en la lista corta" if (row or {}).get("deep")
                          else "fuera de la lista corta: los agentes no corrieron"),
                       rank=(row or {}).get("rank"), score=(row or {}).get("score"),
                       shortlisted=bool((row or {}).get("deep"))))
    if deep:
        steps.append(_agents_step(deep))
        syn = deep.get("synthesis")
        steps.append(_step("sintesis", "Opinión conjunta", "ok" if syn else "sin_datos",
                           (syn or {}).get("thesis") or deep.get("reason") or "sin síntesis",
                           synthesis=syn))
        fc = deep.get("forecast") or {}
        sc = fc.get("scenarios") or {}
        steps.append(_step("proyeccion", "Escenarios", "ok" if sc else "sin_datos",
                           " · ".join(f"{k} {v['p']:.0%}" for k, v in sc.items()) or
                           "sin proyección", horizon_bars=fc.get("horizon_bars"),
                           scenarios={k: v.get("p") for k, v in sc.items()}))
    if opp:
        s = opp["scores"]
        steps.append(_step("oportunidad", "Oportunidad candidata", "ok",
                           f"{opp['side']} a {opp['horizon_bars']} velas; calidad "
                           f"{s['signal_quality']:.2f}, viabilidad {s['viability']:.2f}, "
                           f"riesgo/costos {s['risk_cost']:.2f}",
                           opportunity_id=opp["opportunity_id"], side=opp["side"],
                           valid_until=opp["valid_until"], scores={
                               k: s[k] for k in ("signal_quality", "viability", "risk_cost")}))
        steps.append(_rank_step(rk))
    steps.append(decision(opp, rk, cls, state))
    return {"version": TRACE_VERSION, "mode": "ANALISIS",
            "status_label": view.get("status_label", "candidata, no validada"),
            "trace_id": trace_id_of(view, instrument_id), "instrument_id": instrument_id,
            "symbol": (row or deep or {}).get("symbol"), "asset_class": cls,
            "timeframe": view["universe"]["timeframe"], "asof": view["universe"]["asof"],
            "steps": steps}


def decision(opp: Mapping | None, rk: Mapping | None, cls: str,
             state: Mapping | None) -> dict:
    """La decisión sobre la candidata: nunca validada; visible o en sombra; y qué le falta."""
    lv = rollout.level_of(cls, state)
    if opp is None:
        return _step("decision", "Decisión", "degradado", "sin oportunidad: no hay nada que "
                     "decidir en esta pasada", validated=False, visible=False,
                     level=lv["level"], next=lv["next"])
    shadow = rollout.shadow_reason(opp, state)
    above = bool((rk or {}).get("above_threshold"))
    why = ["no está validada: eso solo lo da la puerta de T49/T101; no alimenta señales visibles "
           "como validadas ni ninguna orden"]
    why.append("supera el umbral del azar" if above else "no supera el umbral del azar")
    if shadow:
        why.append(f"en sombra: {shadow}")
    return _step("decision", "Decisión", "degradado" if shadow else "ok",
                 f"candidata, no validada · nivel {rollout.LEVEL_ES[lv['level']]} · "
                 + ("en sombra" if shadow else "visible"),
                 validated=False, visible=shadow is None, shadow=shadow, level=lv["level"],
                 active=lv["active"], above_threshold=above, why=why, next=lv["next"])
