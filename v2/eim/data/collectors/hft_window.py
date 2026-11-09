"""Aceptación de T78: calidad sostenida en una ventana, no horas perfectas seguidas (T147).

`PLAN/T78.md` §Aceptación pide una corrida continua de ≥ 72 h con cobertura ≥ 99 % de las horas,
ningún hueco sin detectar y ≥ 99 % de coincidencia top-10 con los snapshots REST. Hasta T147 el
código lo medía como 72 horas completas SEGUIDAS (T126) y con dos umbrales por flujo que el
documento no pide (`bbo` y la cadencia de `mark`): una hora al 98,x % reiniciaba la cuenta, así que
la puerta dependía de silencios de red ajenos y castigaba cualquier despliegue propio.

Aquí se mide lo que el documento dice:

- **Ventana** (`window`): el tramo contiguo más largo de horas auditadas con ≥ `HOURS_MIN` de horas
  completas, 0 huecos sin detectar y ≥ `MATCH_MIN` de coincidencia top-10 en todo el tramo. Una
  hora con un hueco sin detectar corta el tramo (condición dura, nunca se afloja); una hora sin QC
  también, salvo mantenimiento. A diferencia de la racha, no vuelve a cero con un tropiezo.
- **Mantenimiento declarado** (`declare_maint`): las horas de un despliegue anunciado no cuentan ni
  rompen la contigüidad, así que desplegar ya no cuesta la corrida (T123/T124).
- **Atribución** (`attribute`): cada hora incompleta queda en «nuestra» (reinicio, cola llena,
  salto de reloj, proceso caído) o «ajena» (silencio o desconexión del exchange). Solo la primera
  es deuda del equipo y materia de la fase 21.
- **Racha** (`streak`, T126): se conserva como lectura informativa durante la transición.

`book_usable_pct` (cobertura agregada del tramo) y `worst_hour` se **informan, no deciden**: la
lectura por cobertura agregada se discute en `PLAN/notas/T147_criterio_t78.md` y adoptarla sería
otra decisión del usuario.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from eim.data.collectors.hft_read import hour_label
from eim.data.collectors.hft_schema import AREA

NEED_H = 72
MATCH_MIN = 0.99
HOURS_MIN = 0.99
MAX_LIST = 24
OUR_CAUSES = ("cola_llena",)
THEIR_CAUSES = ("silencio", "desconexion", "secuencia", "sin_libro")


# --------------------------------------------------------------------------- mantenimiento (E4)

def maint_path(root: str | Path, symbol: str) -> Path:
    return Path(root) / AREA / "qc" / f"symbol={symbol}" / "maintenance.json"


def load_maint(root: str | Path, symbol: str) -> list[dict]:
    """Tramos de mantenimiento declarados (lista vacía si no hay archivo o está roto)."""
    try:
        d = json.loads(maint_path(root, symbol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    ws = d.get("windows") if isinstance(d, dict) else None
    return [w for w in ws if "from_h" in w and "to_h" in w] if isinstance(ws, list) else []


def declare_maint(root: str | Path, symbol: str, h0: int, h1: int, note: str,
                  now_s: float | None = None) -> dict:
    """Declara [h0, h1] (horas UTC, ambas incluidas) como mantenimiento conocido.

    Idempotente por tramo: declarar el mismo dos veces lo deja una sola vez. Solo escribe el
    archivo de mantenimiento; no toca ningún JSON de QC ni la captura."""
    if h1 < h0:
        raise ValueError("la hora final del mantenimiento es anterior a la inicial")
    w = {"from": hour_label(h0), "to": hour_label(h1), "from_h": h0, "to_h": h1,
         "hours": h1 - h0 + 1, "note": str(note)[:300],
         "at": int((now_s if now_s is not None else time.time()) * 1000)}
    ws = [x for x in load_maint(root, symbol) if (x["from_h"], x["to_h"]) != (h0, h1)]
    ws.append(w)
    ws.sort(key=lambda x: x["from_h"])
    p = maint_path(root, symbol)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"symbol": symbol, "windows": ws}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(p)
    return {"declared": w, "windows": len(ws)}


def is_maint(hour: int, maint: list[dict]) -> bool:
    return any(w["from_h"] <= hour <= w["to_h"] for w in maint)


# --------------------------------------------------------------------------- atribución (E3)

def attribute(rep: dict | None, hour: int, maint: list[dict] | None = None) -> str:
    """De quién es una hora incompleta: «mantenimiento», «nuestra», «ajena» o «sin causa».

    `rep` a None = la hora no tiene QC (proceso caído), que es deuda nuestra salvo mantenimiento."""
    if maint and is_maint(hour, maint):
        return "mantenimiento"
    if rep is None:
        return "nuestra"
    causes = (rep.get("gaps_marked") or {}).get("by_cause") or {}
    ours = (rep.get("restarts") or 0) or (rep.get("runs") or 1) > 1 \
        or (rep.get("overflow_dropped") or 0) or ((rep.get("clock") or {}).get("jumps") or 0) \
        or any(causes.get(c) for c in OUR_CAUSES)
    if ours:
        return "nuestra"
    return "ajena" if any(causes.get(c) for c in THEIR_CAUSES) else "sin causa"


# --------------------------------------------------------------------------- ventana (E2)

def _prefix(xs: list[float]) -> list[float]:
    out = [0.0]
    for x in xs:
        out.append(out[-1] + x)
    return out


def _spans(reps: list[dict], maint: list[dict]) -> tuple[list[list[dict]], list[str]]:
    """Tramos contiguos de horas que cuentan. Cortan: una hora sin QC y una hora con huecos sin
    detectar. Las horas de mantenimiento declarado unen el tramo y no cuentan."""
    if not reps:
        return [], []
    by_hour = {r["hour_index"]: r for r in reps}
    spans: list[list[dict]] = [[]]
    broken: list[str] = []
    for h in range(reps[0]["hour_index"], reps[-1]["hour_index"] + 1):
        if is_maint(h, maint):
            continue
        r = by_hour.get(h)
        if r is None:
            spans.append([])
            continue
        if (r.get("holes") or {}).get("undetected"):
            broken.append(r["hour"])
            spans.append([])
            continue
        spans[-1].append(r)
    return [s for s in spans if s], broken


def _valid(i: int, j: int, comp: list[float], cmpb: list[float], mtch: list[float]) -> bool:
    """¿El subtramo [i, j) cumple el % de horas completas y la coincidencia top-10?"""
    if comp[j] - comp[i] < (j - i) * HOURS_MIN:
        return False
    c = cmpb[j] - cmpb[i]
    return not c or (mtch[j] - mtch[i]) / c >= MATCH_MIN


def _best_sub(span: list[dict]) -> tuple[int, int]:
    """El subtramo más largo que cumple la ventana (el más reciente si empatan).

    (0, 0) si ninguno lo cumple."""
    comp = _prefix([1.0 if r["complete"] else 0.0 for r in span])
    cmpb = _prefix([float((r.get("checks") or {}).get("comparable") or 0) for r in span])
    mtch = _prefix([float((r.get("checks") or {}).get("matched") or 0) for r in span])
    best = (0, 0)
    for i in range(len(span)):
        for j in range(len(span), i, -1):
            if j - i < best[1] - best[0]:
                break
            if _valid(i, j, comp, cmpb, mtch):
                best = (i, j)
                break
    return best


_EMPTY = {"hours": 0, "first_hour": None, "last_hour": None, "hours_complete": 0,
          "pct_complete": None, "match_rate": None, "undetected": 0, "book_usable_pct": None,
          "worst_hour": None, "maintenance_h": 0, "incomplete": []}


def _win_info(span: list[dict], i: int, j: int, maint: list[dict]) -> dict:
    run = span[i:j]
    if not run:
        return dict(_EMPTY)
    comp = sum(1 for r in run if r["complete"])
    c = sum((r.get("checks") or {}).get("comparable") or 0 for r in run)
    ok = sum((r.get("checks") or {}).get("matched") or 0 for r in run)
    usable = [r["book_usable"] for r in run if r.get("book_usable") is not None]
    worst = min((r for r in run if r.get("book_usable") is not None),
                key=lambda r: r["book_usable"], default=None)
    inc = [{"hour": r["hour"], "causa": attribute(r, r["hour_index"], maint),
            "book_usable": r.get("book_usable")} for r in run if not r["complete"]]
    return {
        "hours": len(run), "first_hour": run[0]["hour"], "last_hour": run[-1]["hour"],
        "hours_complete": comp, "pct_complete": round(comp / len(run), 4),
        "match_rate": round(ok / c, 4) if c else None, "undetected": 0,
        "book_usable_pct": round(sum(usable) / len(usable), 5) if usable else None,
        "worst_hour": {"hour": worst["hour"], "book_usable": worst["book_usable"]}
        if worst is not None else None,
        "maintenance_h": sum(1 for h in range(run[0]["hour_index"], run[-1]["hour_index"] + 1)
                             if is_maint(h, maint)),
        "incomplete": inc[-MAX_LIST:],
    }


def window(reps: list[dict], fresh_h: int, maint: list[dict] | None = None,
           since_h: int | None = None, need_h: int = NEED_H) -> dict:
    """Veredicto de T78 por ventana (T147). `fresh_h`: hora desde la que una ventana sigue viva.

    `best` decide; `current` es la ventana viva (la que acaba en la última hora auditada), para ver
    lo que falta. `attribution` reparte TODAS las horas incompletas del tramo leído, no solo las de
    la ventana, porque es lo que dice de quién es la deuda."""
    maint = maint or []
    out = {"rule": "ventana (T147)", "need_h": need_h, "hours_min": HOURS_MIN,
           "match_min": MATCH_MIN,
           "since": hour_label(since_h) if since_h is not None else None,
           "audited_hours": len(reps)}
    if not reps:
        return {**out, "best": dict(_EMPTY), "current": dict(_EMPTY), "remaining_h": need_h,
                "passed": False, "attribution": {}, "broken_by_undetected": []}
    spans, broken = _spans(reps, maint)
    best, best_span = (0, 0), []
    cur, cur_span = (0, 0), []
    for span in spans:
        i, j = _best_sub(span)
        if j - i >= best[1] - best[0]:
            best, best_span = (i, j), span
        if span[-1]["hour_index"] >= fresh_h:
            cur, cur_span = (i, j), span
    att: dict[str, int] = {}
    by_hour = {r["hour_index"]: r for r in reps}
    for h in range(reps[0]["hour_index"], reps[-1]["hour_index"] + 1):
        r = by_hour.get(h)
        if r is not None and r["complete"]:
            continue
        k = attribute(r, h, maint)
        att[k] = att.get(k, 0) + 1
    top = _win_info(best_span, best[0], best[1], maint)
    now = _win_info(cur_span, cur[0], cur[1], maint)
    passed = top["hours"] >= need_h
    return {**out, "best": top, "current": now,
            "remaining_h": 0 if passed else max(0, need_h - now["hours"]), "passed": passed,
            "attribution": att, "broken_by_undetected": broken[-MAX_LIST:]}


# ------------------------------------------------------------------ racha (T126) y agregado

def _run_info(run: list[dict]) -> dict:
    comp = sum(r["checks"]["comparable"] for r in run)
    ok = sum(r["checks"]["matched"] for r in run)
    return {"hours": len(run), "first_hour": run[0]["hour"] if run else None,
            "last_hour": run[-1]["hour"] if run else None,
            "match_rate": round(ok / comp, 4) if comp else None,
            "undetected": sum(r["holes"]["undetected"] for r in run)}


def streak(reps: list[dict], fresh_h: int, since_h: int | None = None,
           need_h: int = NEED_H) -> dict:
    """Racha de horas completas seguidas (T126, lectura informativa desde T147): la mayor (`best`)
    y la que sigue viva (`current`), con las horas que le faltan para `need_h`."""
    best, start, prev = (0, 0), 0, None
    for i, r in enumerate(reps):
        h = r["hour_index"]
        if not r["complete"] or (prev is not None and h != prev + 1):
            start = i + 1 if not r["complete"] else i
        if r["complete"] and i + 1 - start > best[1] - best[0]:
            best = (start, i + 1)
        prev = h
    last = reps[-1] if reps else None
    alive = last is not None and last["complete"] and last["hour_index"] >= fresh_h
    cur = _run_info(reps[start:] if alive else [])
    top = _run_info(reps[best[0]:best[1]])
    passed = (top["hours"] >= need_h and top["undetected"] == 0
              and (top["match_rate"] or 0) >= MATCH_MIN)
    return {"rule": "racha (T126, informativa)", "need_h": need_h,
            "since": hour_label(since_h) if since_h is not None else None,
            "audited_hours": len(reps), "best": top, "current": cur,
            "remaining_h": 0 if passed else max(0, need_h - cur["hours"]), "passed": passed}
