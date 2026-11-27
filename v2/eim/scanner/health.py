"""Salud multiactivo (T102): qué mercados vigila el sistema, con qué datos y qué no puede ver.

Función pura: recibe la vista publicada del escáner (`data/scanner/view.json`), su estado
(`status.json`), los recuentos del catálogo y de las exclusiones por clase (si se pudieron leer) y
la hora, y devuelve la salud **por clase** y **por fuente**, el estado del escáner y su presupuesto
de cómputo. La E/S y los avisos viven en `health_service.py`.

Reglas que no se negocian:

- **«Sin datos» nunca es sano.** Una clase habilitada sin instrumentos puntuados, una vista que no
  existe o un escáner que no ha corrido son `sin_datos` y nunca suben a `ok`.
- **Nada se supone.** Lo que no se puede medir queda `None` con su nota (p. ej. el consumo real
  por proveedor: la cola solo conoce su techo declarado).
- **Modo siempre visible**: todo sale en modo ANÁLISIS con el aviso de que nada está validado.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping

from eim.data.providers.meta import SOURCES, lookup
from eim.data.timeframes import tf_ms, tf_offset
from eim.observability.thresholds import stale_after_s
from eim.scanner.params import DEFAULT_PARAMS, ScannerParams

HEALTH_VERSION = "1"
OK, DEGRADED, ERROR, STALE, NO_DATA, PAUSED, PLANNED = (
    "ok", "degradado", "error", "obsoleto", "sin_datos", "pausado", "planeado")
#: Gravedad para el estado global (más bajo = peor). `planeado` no cuenta en el global.
SEVERITY = {ERROR: 0, NO_DATA: 1, STALE: 2, DEGRADED: 3, PAUSED: 4, OK: 5, PLANNED: 6}
#: Cadencia del escáner: la tarea diaria de T95 (00:45 UTC). Degradado a 1,5 cadencias sin vista
#: nueva; obsoleto a `stale_after_s` (3 cadencias, la regla del observatorio de T72).
CADENCE_S = 86_400
DEGRADED_AFTER_S = int(1.5 * CADENCE_S)
#: Peso de una petición de velas con `limit=1000` en Binance (lo que razona `params.rate_limits`).
KLINES_WEIGHT = 5
CANDIDATE_TOP = 5
SCANNER_SOURCE = "binance-futures (escáner global, T93)"   # `scanner_market.SOURCE`

ENABLED, WATCH, INFO_ONLY, DROPPED = ("habilitada", "en observación", "solo información",
                                      "descartada")
#: Qué se espera de cada clase hoy (decisiones de T87, T95, T97, T100) y qué tarea la mueve.
CLASS_PLAN: dict[str, tuple[str, str, str]] = {
    "crypto": (ENABLED, "T93", "Banco de pruebas: perpetuos USDⓈ-M de Binance."),
    "equity": (WATCH, "T97", "Solo perpetuos TradFi de Binance (nivel 1, historia corta); la "
                             "clase propia está en pausa hasta la revisión del 2026-12-29."),
    "etf": (WATCH, "T97", "Sin proveedor aprobado; solo perpetuos de Binance si los hay."),
    "index": (WATCH, "T97", "Solo perpetuos de Binance sobre índices; la clase propia es T97."),
    "fx": (WATCH, "T98", "Solo perpetuos de Binance sobre divisas; la clase propia es T98."),
    "commodity": (WATCH, "T99", "Solo perpetuos de Binance sobre materias primas (T99)."),
    "future": (WATCH, "T99", "Futuros con vencimiento: fuera del universo (solo perpetuos)."),
    "option": (INFO_ONLY, "T213", "Opciones cripto solo como dato de volatilidad si se aprueba "
                                  "la fuente; nunca se operan."),
    "bond": (DROPPED, "T100", "Renta fija: solo modelos y curvas como dato (decisión de T100)."),
    "cash": (DROPPED, "T100", "Monetario: fuera del alcance (decisión de T100)."),
}
LABEL_ES = {"crypto": "Cripto", "equity": "Acciones", "etf": "ETF", "index": "Índices",
            "fx": "Divisas", "commodity": "Materias primas", "future": "Futuros",
            "option": "Opciones", "bond": "Renta fija", "cash": "Monetario"}


def class_of(instrument_id: str) -> str:
    """Clase a partir del id del registro (`crypto.binance.usdm.BTCUSDT` → `crypto`)."""
    return instrument_id.split(".", 1)[0]


def worst(states: list[str]) -> str:
    live = [s for s in states if s != PLANNED]
    return min(live, key=lambda s: SEVERITY[s]) if live else NO_DATA


def freshness(view: Mapping | None, now: int) -> tuple[str, float | None]:
    """(estado, horas desde la última vista publicada)."""
    if not view or not view.get("generated_at"):
        return NO_DATA, None
    age_s = max(0.0, (now - int(view["generated_at"])) / 1000)
    lim = stale_after_s(CADENCE_S) or CADENCE_S * 3
    state = STALE if age_s > lim else DEGRADED if age_s > DEGRADED_AFTER_S else OK
    return state, round(age_s / 3600, 2)


def _stale_rows(rows: list[Mapping], asof: int, p: ScannerParams) -> int:
    """Filas cuya última vela es más vieja que la última cerrada más el margen de su clase."""
    try:
        step, off = tf_ms(p.timeframe), tf_offset(p.timeframe)
    except ValueError:
        return 0
    newest = ((asof - off) // step) * step + off - step       # apertura de la última cerrada
    return sum(1 for r in rows if r.get("last_t") is not None
               and (newest - int(r["last_t"])) / step > p.grace(r["asset_class"]))


def _class_row(cls: str, rows: list[Mapping], opps: list[Mapping], above: int,
               excl: Mapping[str, int] | None, mk: list[Mapping], view_state: str,
               asof: int, p: ScannerParams) -> dict:
    plan, task, note = CLASS_PLAN.get(cls, (WATCH, "T87", "Clase sin plan escrito."))
    n = len(rows)
    n_excl = sum(excl.values()) if excl is not None else None
    cov = None if n_excl is None or n + n_excl == 0 else round(n / (n + n_excl), 4)
    q = [float(r["quality"]) for r in rows if r.get("quality") is not None]
    stale = _stale_rows(rows, asof, p) if rows else 0
    opened = sum(int(m.get("abierto", 0)) for m in mk)
    closed = sum(int(m.get("cerrado", 0)) for m in mk)
    nocal = sum(int(m.get("sin_calendario", 0)) for m in mk)
    reasons: list[str] = []
    if plan == DROPPED:
        state = PLANNED
        reasons.append("fuera del alcance por decisión escrita")
    elif plan == INFO_ONLY and n == 0:
        state = PLANNED
        reasons.append("sin fuente aprobada todavía")
    elif view_state == NO_DATA or n == 0:
        state = NO_DATA
        reasons.append("ningún instrumento puntuado en la última vista" if view_state != NO_DATA
                       else "el escáner aún no publicó su vista")
    else:
        state = view_state
        if view_state != OK:
            reasons.append("la vista del escáner no está al día")
        if stale and stale / n > 0.2:
            state = worst([state, DEGRADED])
            reasons.append(f"{stale} de {n} con datos viejos")
        if q and min(q) < 1.0 and sum(x < 1.0 for x in q) / len(q) > 0.5:
            state = worst([state, DEGRADED])
            reasons.append("más de la mitad con calidad de datos incompleta")
        if nocal and nocal == n:
            state = worst([state, DEGRADED])
            reasons.append("sin calendario: no se sabe si su mercado está abierto")
    return {
        "asset_class": cls, "label": LABEL_ES.get(cls, cls), "plan": plan, "task": task,
        "note": note, "state": state, "alerting": plan == ENABLED, "n_scored": n,
        "n_excluded": n_excl, "coverage": cov, "exclusions": dict(excl or {}),
        "quality_mean": round(sum(q) / len(q), 4) if q else None,
        "quality_incomplete": sum(x < 1.0 for x in q), "stale_rows": stale,
        "markets": {"abierto": opened, "cerrado": closed, "sin_calendario": nocal},
        "candidates": len(opps), "above_threshold": above,
        "top": [{"instrument_id": o["instrument_id"], "symbol": o["symbol"], "side": o["side"],
                 "opportunity_id": o["opportunity_id"]} for o in opps[:CANDIDATE_TOP]],
        "reasons": reasons,
    }


def _usage(rate_per_s: float | None, meta) -> tuple[float | None, str]:
    if rate_per_s is None or not meta.rate_limit_per_min:
        return None, "sin techo declarado en la cola o sin límite publicado"
    share = rate_per_s * 60 * KLINES_WEIGHT / meta.rate_limit_per_min
    return round(share, 4), (f"techo declarado de la cola: {rate_per_s * 60:.0f} llamadas/min × "
                             f"peso {KLINES_WEIGHT} de {meta.rate_limit_per_min}/min; el consumo "
                             "real por proveedor no se mide todavía")


def _providers(view: Mapping | None, classes: list[dict], failed: int, view_state: str,
               p: ScannerParams) -> list[dict]:
    used: dict[str, set[str]] = defaultdict(set)
    for o in (view or {}).get("opportunities", []):
        used[lookup(o.get("source")).name].add(o["asset_class"])
    if view:                       # todo el universo puntuado sale del almacén de Binance (T93)
        used[lookup(SCANNER_SOURCE).name] |= {c["asset_class"] for c in classes if c["n_scored"]}
    out = []
    for name in sorted(set(SOURCES) | set(used)):
        meta = SOURCES.get(name) or lookup(name)
        on = name in used
        rate = p.rate_limits.get(name.split("-", 1)[0]) if on else None
        share, note = _usage(rate, meta) if on else (None, "no la usa el escáner")
        state = (worst([view_state, DEGRADED if failed else OK]) if on else PLANNED)
        out.append({"name": name, "used": on, "classes": sorted(used.get(name, ())),
                    "level": meta.coverage, "license": meta.license,
                    "delay_ms": meta.delay_ms, "rate_limit_per_min": meta.rate_limit_per_min,
                    "usage_share": share, "usage_note": note, "errors": failed if on else 0,
                    "state": state})
    return out


def _scanner(view: Mapping | None, status: Mapping | None, view_state: str) -> dict:
    st = status or {}
    sweep = st.get("last_sweep") or {}
    queue = st.get("queue") or {}
    rk = (view or {}).get("ranking") or {}
    deep_run = next((r for r in (view or {}).get("runs", []) if r.get("rhythm") == "agentes"),
                    None)
    failed = len(((deep_run or {}).get("detail") or {}).get("failed") or [])
    deep_ms = sum(float(d.get("elapsed_ms") or 0) for d in (view or {}).get(
        "instruments", {}).values())
    reasons = []
    state = view_state
    if failed:
        state = worst([state, DEGRADED])
        reasons.append(f"{failed} trabajos de agentes fallaron en la última pasada")
    if sweep and sweep.get("within_budget") is False:
        state = worst([state, DEGRADED])
        reasons.append("el embudo superó su presupuesto de cómputo")
    if view and not rk.get("available"):
        state = worst([state, DEGRADED])
        reasons.append("sin ranking: " + str(rk.get("error") or rk.get("reason") or "—"))
    thr = rk.get("threshold") or {}
    return {
        "state": state, "reasons": reasons, "failed_jobs": failed,
        "queue": {k: int(queue.get(k, 0)) for k in ("pending", "running", "done", "failed")},
        "last_sweep": {k: sweep.get(k) for k in ("run_id", "asof", "n_catalog", "n_stage1",
                                                 "n_stage2", "n_scored", "n_shortlist")},
        "budget": {"ms_per_instrument": sweep.get("ms_per_instrument"),
                   "budget_ms": DEFAULT_PARAMS.budget_ms_per_instrument,
                   "within_budget": sweep.get("within_budget"),
                   "deep_ms_total": round(deep_ms, 1),
                   "deep_ms_per_instrument": round(deep_ms / max(1, len(
                       (view or {}).get("instruments", {}))), 1),
                   "max_procs": DEFAULT_PARAMS.max_procs},
        "ranking": {"available": bool(rk.get("available")), "threshold_status": thr.get("status"),
                    "threshold": thr.get("value"), "p_global": thr.get("p_global"),
                    "n_above": rk.get("n_above"),
                    "family_total": (rk.get("family") or {}).get("total"),
                    "matured": (rk.get("family") or {}).get("matured")},
    }


def blind_spots(view: Mapping | None, exclusions: Mapping[str, int] | None) -> list[str]:
    """Lo que el sistema NO puede ver, en palabras: exclusiones, agentes sin datos, clases fuera."""
    out = []
    if not view:
        return ["el escáner no ha publicado ninguna vista: no se vigila ningún mercado"]
    for reason, n in sorted((exclusions or view["universe"].get("exclusions") or {}).items(),
                            key=lambda x: -x[1]):
        out.append(f"{n} instrumentos fuera del embudo por «{reason}»")
    for note, n in (view["universe"].get("notes") or {}).items():
        out.append(f"{note.replace('_', ' ')}: {n}")
    skipped = Counter(s["reason"].split(":")[0].split(";")[0]
                      for d in view.get("instruments", {}).values()
                      for s in d.get("skipped") or [])
    for why, n in skipped.most_common(6):
        out.append(f"agente omitido {n} veces: {why}")
    return out


def build(view: Mapping | None, status: Mapping | None, now: int, *,
          excl_by_class: Mapping[str, Mapping[str, int]] | None = None,
          params: ScannerParams = DEFAULT_PARAMS) -> dict:
    """La salud completa (pura). `excl_by_class` = {clase: {motivo: n}} del último barrido."""
    view_state, age_h = freshness(view, now)
    rows = (view or {}).get("universe", {}).get("rows", []) if view else []
    opps = (view or {}).get("opportunities", []) if view else []
    rk_rows = ((view or {}).get("ranking") or {}).get("rows") or []
    above = Counter(class_of(r["instrument_id"]) for r in rk_rows if r.get("above_threshold"))
    by_rows, by_opps, by_mk = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in rows:
        by_rows[r["asset_class"]].append(r)
    for o in opps:
        by_opps[o["asset_class"]].append(o)
    for m in (view or {}).get("universe", {}).get("markets", []) if view else []:
        by_mk[m["asset_class"]].append(m)
    asof = int((view or {}).get("universe", {}).get("asof") or now) if view else now
    names = list(CLASS_PLAN) + sorted(set(by_rows) - set(CLASS_PLAN))
    classes = [_class_row(c, by_rows[c], by_opps[c], above[c],
                          None if excl_by_class is None else excl_by_class.get(c, {}),
                          by_mk[c], view_state, asof, params) for c in names]
    scanner = _scanner(view, status, view_state)
    providers = _providers(view, classes, scanner["failed_jobs"], view_state, params)
    excl_total: Counter = Counter()
    for d in (excl_by_class or {}).values():
        excl_total.update(d)
    watched = [c for c in classes if c["n_scored"]]
    overall = worst([c["state"] for c in classes if c["alerting"]] + [scanner["state"]])
    return {
        "version": HEALTH_VERSION, "mode": "ANALISIS", "generated_at": now,
        "notice": "Salud de la vigilancia multiactivo en modo Análisis: nada de esto es una orden "
                  "ni una señal validada.",
        "overall": overall, "view": {"state": view_state, "age_h": age_h,
                                     "asof": (view or {}).get("universe", {}).get("asof")
                                     if view else None,
                                     "timeframe": params.timeframe},
        "watching": {"classes": [c["asset_class"] for c in watched],
                     "n_instruments": sum(c["n_scored"] for c in watched)},
        "classes": classes, "providers": providers, "scanner": scanner,
        "blind_spots": blind_spots(view, excl_total or None),
    }
