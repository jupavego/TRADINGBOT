"""Publicador puro de sugerencias validadas (T50): ideas vivas × veredictos de T49 → ≤ 3 tarjetas.

Entradas: las ideas del bróker simulado (de cualquier estrategia del catálogo), la última vela
cerrada de cada marco, el precio actual y los veredictos vigentes. Salida: oportunidades solo de
versiones VALIDADAS (se cruza por `estrategia@marco` y huella de la versión), ordenadas por el
límite inferior del IC95 % del R medio fuera de muestra, sin repetidas y sin vencidas; o la lista
vacía con su motivo. Sin I/O, sin red; `suggest()` de síntesis no interviene.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from eim.paper.ideas import HOUR_MS, Idea

STATE = "sugerida_no_ejecutada"
SIN_VALIDADAS, SIN_SENAL, DATOS_VIEJOS, OK = "sin_validadas", "sin_senal", "datos_viejos", "ok"
NOTE = ("Oportunidad potencial. Evidencia de un bróker simulado; no garantiza rentabilidad. "
        "Análisis: no es una orden ni una operación ejecutada.")


class PublishParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    timeframes: tuple[str, ...] = ("15m", "1h")    # intradía
    max_hold_h: float = 36.0                       # tenencia máxima de la idea
    max_setups: int = 3
    dedup_atr: float = 0.5                         # mismo lado y entradas a menos de 0,5 ATR
    entry_tol_atr: float = 0.5                     # mercado: el precio ya se alejó de la entrada
    verdicts_max_age_h: float = 8.0                # se recalculan cada 4 h
    heartbeat_max_age_min: float = 30.0            # latido del bróker (sondea cada ~1 min)


@dataclass(frozen=True)
class Publication:
    status: str
    message: str
    setups: list[dict] = field(default_factory=list)
    validation: dict = field(default_factory=dict)
    discarded: list[dict] = field(default_factory=list)   # ideas validadas que vencieron

    def to_json(self) -> dict:
        return {"status": self.status, "message": self.message, "setups": self.setups,
                "validation": self.validation, "discarded": self.discarded}


def _check(v: dict, cid: str) -> dict:
    return next((c.get("value") or {} for c in v.get("checks", []) if c["id"] == cid), {})


def evidence_of(v: dict) -> dict:
    """Evidencia fuera de muestra de un veredicto: lo mismo que decidió su validación."""
    v2, v3, v4, v5, v6 = (_check(v, c) for c in ("V2", "V3", "V4", "V5", "V6"))
    ci = v2.get("ci") or [None, None]
    return {"n_oos": v.get("n_oos"), "mean_r": v2.get("mean_r"), "ci95": ci,
            "p_holm": v3.get("p_holm"), "max_dd": v4.get("max_dd"),
            "win_rate": (v.get("extras") or {}).get("win_rate"), "cost_r": v6.get("cost_r"),
            "n_live": v5.get("n_live"), "mean_live": v5.get("mean_live"),
            "oos_from": (v.get("oos") or {}).get("from"), "oos_to": (v.get("oos") or {}).get("to")}


def _ci_low(v: dict) -> float:
    lo = evidence_of(v)["ci95"][0]
    return float("-inf") if lo is None else float(lo)


def expired(i: Idea, price: float, now: int, atr: float, p: PublishParams) -> str | None:
    """Motivo por el que una idea ya no es una oportunidad, o None si sigue vigente."""
    if (price - i.sl) * i.side <= 0:
        return "el precio ya está más allá del SL"
    if (i.tp - price) * i.side <= 0:
        return "el precio ya alcanzó el TP"
    if i.kind == "limit":
        if now > i.t + i.fill_ms:
            return "la orden límite está fuera de su ventana"
        if (price - i.entry) * i.side <= 0:
            return "el precio ya llegó a la entrada (orden llenada)"
    elif abs(price - i.entry) > p.entry_tol_atr * atr:
        return f"el precio se alejó más de {p.entry_tol_atr:g} ATR de la entrada"
    return None


def _setup(i: Idea, v: dict) -> dict:
    return {
        "side": "long" if i.side > 0 else "short", "kind": i.kind, "entry": i.entry, "sl": i.sl,
        "tp": i.tp, "rr": i.rr, "strategy": i.strategy, "timeframe": i.timeframe,
        "version": f"v{v['n']}", "id": v["id"], "reason": "; ".join(i.why),
        "hours": i.hold_ms / HOUR_MS, "created_at": i.t,
        "valid_until": i.t + i.fill_ms if i.kind == "limit" else None,
        "state": STATE, "evidence": evidence_of(v)}


def _stale(now: int, verdicts_asof: int | None, heartbeat: int | None, view_stale: bool,
           p: PublishParams) -> str | None:
    if verdicts_asof is None:
        return "aún no hay veredictos de validación calculados"
    if now - verdicts_asof > p.verdicts_max_age_h * HOUR_MS:
        return f"los veredictos tienen más de {p.verdicts_max_age_h:g} h"
    if heartbeat is None:
        return "el servicio del bróker simulado no está en marcha"
    if now - heartbeat > p.heartbeat_max_age_min * 60_000:
        return f"el latido del bróker simulado tiene más de {p.heartbeat_max_age_min:g} min"
    if view_stale:
        return "el bróker simulado está recalculando con datos nuevos"
    return None


def publish(ideas: Sequence[Idea], verdicts: Sequence[dict], *, now: int, price: float | None,
            atr: float | None, last_t: Mapping[str, int | None], verdicts_asof: int | None,
            heartbeat: int | None, view_stale: bool = False,
            params: PublishParams | None = None, review: Collection[str] = ()) -> Publication:
    """`ideas`: propuestas del bróker (cualquiera; aquí se filtra a la última vela cerrada de
    cada marco `last_t`); `verdicts`: veredictos vigentes de T49 (`Verdict.to_json()`);
    `review`: ids de versión «en revisión» por degradación (T51), excluidas hasta un veredicto
    nuevo."""
    p = params or PublishParams()
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    ok = {(v["sid"], v["fingerprint"]): v for v in verdicts
          if v["verdict"] == "VALIDADA" and v.get("retired") is None
          and v["timeframe"] in p.timeframes}
    held = sorted(v["id"] for v in ok.values() if v["id"] in review)
    ok = {k: v for k, v in ok.items() if v["id"] not in review}
    info = {"counts": counts, "validated": sorted(v["id"] for v in ok.values()),
            "attempts": len(verdicts), "in_review": held}
    why = _stale(now, verdicts_asof, heartbeat, view_stale, p)
    if why is None and (price is None or not atr or atr <= 0):
        why = "sin precio actual del bróker simulado"
    if why:
        return Publication(DATOS_VIEJOS, f"Datos desactualizados: {why}.", validation=info)
    if not ok:
        obs, rej = counts.get("EN OBSERVACIÓN", 0), counts.get("RECHAZADA", 0)
        rev = f"; {len(held)} validada(s) en revisión por degradación" if held else ""
        return Publication(
            SIN_VALIDADAS, "Ninguna estrategia pasa todavía la puerta de validación "
            f"({obs} en observación, {rej} rechazadas{rev}).", validation=info)
    live, gone = [], []
    for i in ideas:
        v = ok.get((i.sid, i.version))
        if (v is None or i.timeframe not in p.timeframes or i.hold_ms > p.max_hold_h * HOUR_MS
                or last_t.get(i.timeframe) != i.t):
            continue
        cause = expired(i, float(price), now, float(atr), p)
        if cause:
            gone.append({"id": v["id"], "reason": cause})
        else:
            live.append((i, v))
    live.sort(key=lambda x: (-_ci_low(x[1]), -x[0].conf, x[0].sid, x[0].id))
    kept: list[tuple[Idea, dict]] = []
    for i, v in live:
        if any(k.side == i.side and abs(k.entry - i.entry) < p.dedup_atr * float(atr)
               for k, _ in kept):
            continue
        kept.append((i, v))
        if len(kept) == p.max_setups:
            break
    if not kept:
        return Publication(
            SIN_SENAL, f"Hay {len(ok)} versión(es) validada(s), pero ninguna propone una "
            "operación vigente en la última vela cerrada.", validation=info, discarded=gone)
    return Publication(OK, f"{len(kept)} oportunidad(es) de estrategias validadas.",
                       [_setup(i, v) for i, v in kept], info, gone)
