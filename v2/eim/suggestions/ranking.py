"""Ranking de las tres posiciones sugeridas y embudo de estados de cada oportunidad (T122).

Puro, sin I/O ni red. Las tres posiciones solo las ocupa una oportunidad VALIDADA por la puerta de
T49 y vigente, en el orden del publicador (`publisher._dedup`): límite inferior del IC95 % del R
medio fuera de muestra, que ya integra acierto, relación beneficio/riesgo, costos y la
incertidumbre de la muestra. Una posición sin oportunidad validada queda VACÍA con su motivo:
nunca se rellena con una idea en observación ni con una señal inventada.

El «acierto» de cada posición es la frecuencia observada fuera de muestra en el bróker simulado,
con su intervalo de Wilson: NO es una probabilidad calibrada de esa operación concreta.

El embudo clasifica cada idea de la última vela cerrada de 15 m y 1 h con datos reales:
identificada (la propuso una estrategia) → analizada (tiene veredicto de la puerta) → validada
→ en el ranking; o pendiente de confirmación (en observación) o descartada (con su motivo).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Collection, Mapping, Sequence

from eim.paper.ideas import HOUR_MS, Idea
from eim.suggestions.publisher import (
    DATOS_VIEJOS,
    SIN_SENAL,
    SIN_VALIDADAS,
    Publication,
    PublishParams,
    expired,
)

SLOTS = 3
DEAD = ("CANCELADA", "RECHAZADA", "CERRADA")   # la sombra del bróker ya la descartó o resolvió
ORDER_RULE = ("límite inferior del IC95 % del R medio fuera de muestra (mayor primero); "
              "desempate: confianza de la estrategia")
SUCCESS_NOTE = ("Frecuencia de acierto observada fuera de muestra en el bróker simulado; no es "
                "una probabilidad calibrada de esta operación.")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Intervalo de Wilson al 95 % de una proporción k/n (None sin muestra)."""
    if n <= 0:
        return None
    p, z2 = k / n, z * z
    d = 1 + z2 / n
    c = (p + z2 / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def success_of(ev: Mapping) -> dict:
    """Acierto fuera de muestra de la evidencia de un veredicto, con su IC de Wilson."""
    n, wr = int(ev.get("n_oos") or 0), ev.get("win_rate")
    if wr is None or n <= 0:
        return {"win_rate": None, "n": n, "wins": None, "ci95": None, "calibrated": False,
                "note": "Sin operaciones fuera de muestra: no hay frecuencia de acierto."}
    k = round(float(wr) * n)
    return {"win_rate": float(wr), "n": n, "wins": k, "ci95": list(wilson(k, n) or ()),
            "calibrated": False, "note": SUCCESS_NOTE}


def invalidation(s: Mapping, atr: float | None, p: PublishParams) -> list[dict]:
    """Condiciones que retiran la oportunidad del panel: las mismas de `publisher.expired`."""
    out = [{"kind": "sl", "price": s["sl"]}, {"kind": "tp", "price": s["tp"]}]
    if s["kind"] == "limit":
        out += [{"kind": "window", "until": s["valid_until"]},
                {"kind": "filled", "price": s["entry"]}]
    elif atr:
        d = p.entry_tol_atr * atr
        out.append({"kind": "drift", "lo": s["entry"] - d, "hi": s["entry"] + d,
                    "atr_k": p.entry_tol_atr})
    return out


def risks(s: Mapping) -> list[dict]:
    """Avisos del contexto con el que se decidió la idea (solo datos registrados en la idea)."""
    side = 1 if s["side"] == "long" else -1
    ctx, ev, out = s.get("context") or {}, s["evidence"], []
    if (ctx.get("htf") or 0) < 0:
        out.append({"kind": "htf_against"})
    if (ctx.get("syn_bias") or 0.0) * side < 0:
        out.append({"kind": "synthesis_against", "bias": ctx["syn_bias"]})
    if ev.get("max_dd") is not None:
        out.append({"kind": "max_dd", "value": ev["max_dd"]})
    if ev.get("n_live") == 0:
        out.append({"kind": "no_live"})
    return out


def _empty(pub: Publication, filled: int) -> str:
    if pub.status == DATOS_VIEJOS:
        return pub.message
    if pub.status == SIN_VALIDADAS:
        return "Sin oportunidad validada: ninguna estrategia pasa todavía la puerta de validación."
    if pub.status == SIN_SENAL:
        return ("Sin oportunidad validada vigente: las versiones validadas no proponen una "
                "operación en la última vela cerrada.")
    return (f"Solo {filled} oportunidad(es) validada(s) vigente(s): esta posición queda vacía "
            "(no se rellena con ideas sin validar).")


def ranking(pub: Publication, *, atr: float | None, statuses: Mapping[str, str],
            params: PublishParams | None = None, slots: int = SLOTS) -> list[dict]:
    """Siempre `slots` posiciones: las validadas en su orden y el resto vacías con su motivo.
    `statuses`: estado de cada idea en la sombra del bróker simulado (id de idea → estado)."""
    p = params or PublishParams()
    out = []
    for k in range(slots):
        if k >= len(pub.setups):
            out.append({"rank": k + 1, "state": "vacia", "index": None,
                        "message": _empty(pub, len(pub.setups))})
            continue
        s = pub.setups[k]
        out.append({"rank": k + 1, "state": "validada", "index": k,
                    "order": {"rule": ORDER_RULE, "ci_low": s["evidence"]["ci95"][0]},
                    "success": success_of(s["evidence"]),
                    "invalidation": invalidation(s, atr, p), "risks": risks(s),
                    "sim_status": statuses.get(s.get("idea_id", ""))})
    return out


def _discarded(i: Idea, v: dict, status: str, pub: Publication, review: Collection[str],
               price: float | None, atr: float | None, now: int, p: PublishParams) -> str | None:
    """Motivo por el que una idea analizada no está en el ranking; None = pendiente."""
    if v.get("retired") is not None:
        return "versión retirada"
    if v["verdict"] == "RECHAZADA":
        return "rechazada por la puerta de validación (T49)"
    if v["verdict"] != "VALIDADA":
        return None                                  # en observación: pendiente de confirmación
    if v["id"] in review:
        return "validada, en revisión por degradación (T51)"
    if status in DEAD:
        return f"el bróker simulado la dio por {status.lower()}"
    if i.hold_ms > p.max_hold_h * HOUR_MS:
        return f"tenencia mayor que {p.max_hold_h:g} h (no es intradía)"
    if pub.status == DATOS_VIEJOS or price is None or not atr:
        return "no se publica: datos desactualizados"
    return expired(i, price, now, atr, p) or "duplicada o fuera de las tres primeras"


def funnel(cands: Sequence[tuple[Idea, str]], verdicts: Sequence[dict], pub: Publication, *,
           last_t: Mapping[str, int | None], now: int, price: float | None, atr: float | None,
           review: Collection[str] = (), params: PublishParams | None = None) -> dict:
    """Embudo de la última vela cerrada de cada marco intradía. `cands`: (idea, estado en la
    sombra del bróker) de todas las ideas de esos marcos, también las ya descartadas."""
    p = params or PublishParams()
    by_key = {(v["sid"], v["fingerprint"]): v for v in verdicts if v["timeframe"] in p.timeframes}
    ranked = {s.get("idea_id") for s in pub.setups}
    n = Counter({k: 0 for k in ("identified", "analyzed", "validated", "ranked", "pending",
                                "discarded", "unanalyzed")})
    reasons: Counter[str] = Counter()
    for i, status in cands:
        if i.timeframe not in p.timeframes or last_t.get(i.timeframe) != i.t:
            continue
        n["identified"] += 1
        v = by_key.get((i.sid, i.version))
        if v is None:
            n["unanalyzed"] += 1
            continue
        n["analyzed"] += 1
        if v["verdict"] == "VALIDADA" and v.get("retired") is None and v["id"] not in review:
            n["validated"] += 1
        if i.id in ranked:
            n["ranked"] += 1
            continue
        why = _discarded(i, v, status, pub, review, price, atr, now, p)
        if why is None:
            n["pending"] += 1
        else:
            n["discarded"] += 1
            reasons[why] += 1
    return {**n, "timeframes": list(p.timeframes),
            "candles": {tf: last_t.get(tf) for tf in p.timeframes},
            "reasons": [{"reason": r, "n": c} for r, c in reasons.most_common()]}
