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
- **Atribución** (`hft_attrib.py`): cada hora incompleta queda en «nuestra» (reinicio, cola llena,
  salto de reloj, proceso caído, tiempo perdido que nadie marcó) o «ajena» (silencio o
  desconexión del exchange). Solo la primera es deuda del equipo y materia de la fase 21. La regla
  se afinó en T148 E3, porque un proceso muerto se parecía por dentro a un exchange callado.
- **Racha** (`streak`, T126): se conserva como lectura informativa durante la transición.

`book_usable_pct` (cobertura agregada del tramo) y `worst_hour` se **informan, no deciden**: la
lectura por cobertura agregada se discute en `PLAN/notas/T147_criterio_t78.md` y adoptarla sería
otra decisión del usuario.
"""

from __future__ import annotations

from collections.abc import Container

from eim.data.collectors.hft_attrib import (  # noqa: F401 - API estable: hft_window.<lo de antes>
    OUR_CAUSES,
    THEIR_CAUSES,
    attribute,
    declare_maint,
    is_maint,
    load_maint,
    maint_path,
    unmarked_s,
    why,
)
from eim.data.collectors.hft_read import hour_label

NEED_H = 72
MATCH_MIN = 0.99
HOURS_MIN = 0.99
MAX_LIST = 24


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


def _win_info(span: list[dict], i: int, j: int, maint: list[dict],
              blind: Container[int] | None = None) -> dict:
    run = span[i:j]
    if not run:
        return dict(_EMPTY)
    comp = sum(1 for r in run if r["complete"])
    c = sum((r.get("checks") or {}).get("comparable") or 0 for r in run)
    ok = sum((r.get("checks") or {}).get("matched") or 0 for r in run)
    usable = [r["book_usable"] for r in run if r.get("book_usable") is not None]
    worst = min((r for r in run if r.get("book_usable") is not None),
                key=lambda r: r["book_usable"], default=None)
    inc = [{"hour": r["hour"], "causa": attribute(r, r["hour_index"], maint, blind),
            "motivo": why(r, r["hour_index"], maint, blind),
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
           since_h: int | None = None, need_h: int = NEED_H,
           blind_hours: Container[int] | None = None) -> dict:
    """Veredicto de T78 por ventana (T147). `fresh_h`: hora desde la que una ventana sigue viva.

    `best` decide; `current` es la ventana viva (la que acaba en la última hora auditada), para ver
    lo que falta. `attribution` reparte TODAS las horas incompletas del tramo leído, no solo las de
    la ventana, porque es lo que dice de quién es la deuda. `blind_hours`: las horas que el
    registro de consumo no vio (T148 E2), que la atribución cuenta como nuestras."""
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
        k = attribute(r, h, maint, blind_hours)
        att[k] = att.get(k, 0) + 1
    top = _win_info(best_span, best[0], best[1], maint, blind_hours)
    now = _win_info(cur_span, cur[0], cur[1], maint, blind_hours)
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
