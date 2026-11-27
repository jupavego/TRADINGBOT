"""Órdenes de la salud multiactivo (T102). Desde `v2/`:

    python -m eim.scanner health [--json] [--summary F] [--quiet]   # revisión: salud, despliegue,
                                                                    # avisos y eventos por lotes
    python -m eim.scanner trace INSTRUMENT_ID [--json] [--summary F] # recorrido de una candidata
    python -m eim.scanner trace --first                              # el de la primera candidata

`health` no barre ni corre agentes: revisa lo último publicado. Si el escáner está en marcha y su
base está ocupada, revisa sin las exclusiones por clase (cobertura «no medida») en vez de esperar.
Códigos: `health` 0 sano o degradado · 3 sin datos u obsoleto · 4 error; `trace` 0 · 5 sin ese
instrumento en la última vista.
"""

from __future__ import annotations

import json
from pathlib import Path

from eim.scanner import health as H

CODES = {H.OK: 0, H.DEGRADED: 0, H.PAUSED: 0, H.NO_DATA: 3, H.STALE: 3, H.ERROR: 4}


def _exclusions(data_dir: Path) -> dict | None:
    """Exclusiones por clase del último barrido; None si la base no existe o está ocupada."""
    if not (data_dir / "scanner" / "scanner.duckdb").exists():
        return None
    try:
        from eim.data.scanner_store import open_scanner_store

        st = open_scanner_store(data_dir)
    except Exception:  # noqa: BLE001 - ocupada por el servicio: se revisa sin ellas
        return None
    try:
        last = st.last_run("profundo")
        return st.exclusions_by_class(last["run_id"]) if last else None
    finally:
        st.close()


def line(h: dict) -> str:
    cls = [c for c in h["classes"] if c["n_scored"] or c["alerting"]]
    parts = [f"{c['label']} {c['state']} ({c['n_scored']}"
             + ("" if c["coverage"] is None else f", cobertura {c['coverage']:.0%}")
             + f", {c['candidates']} candidatas)" for c in cls]
    ob = h.get("observability") or {}
    lv = {u["id"]: u["level"] for u in (h.get("rollout") or {}).get("units", {}).values()
          if u["kind"] == "class"}
    return (f"salud T102: {h['overall']}; vista hace {h['view']['age_h']} h; "
            + "; ".join(parts)
            + f"; niveles {', '.join(f'{k} {v}' for k, v in sorted(lv.items())) or '—'}"
            + f"; avisos activos {len(h.get('alerts_active') or {})}"
            + f"; observatorio {ob.get('events', 0)} eventos en "
            f"{ob.get('build_ms', 0) + ob.get('emit_ms', 0):.1f} ms "
            f"({'dentro' if ob.get('within', True) else 'FUERA'} del umbral)")


def health_cmd(data_dir: Path, a) -> int:
    from eim.observability.emit import configure, flush
    from eim.operation import priority
    from eim.scanner import health_service

    configure(process="scanner", spool_dir=data_dir / "obs" / "spool")
    priority.apply_role("scanner")  # T126: prescindible, prioridad baja (si EIM_PRIORITY)
    h = health_service.check(data_dir, excl_by_class=_exclusions(data_dir),
                             sinks=[] if a.quiet else None)
    flush(2.0)
    text = line(h)
    print(json.dumps(h, ensure_ascii=False, indent=1) if a.json else text)
    if a.summary:
        Path(a.summary).write_text(text, encoding="utf-8")
    return CODES.get(h["overall"], 3)


def trace_cmd(data_dir: Path, a) -> int:
    from eim.data.scanner_view import read_view
    from eim.scanner import health_service, trace

    view = read_view(data_dir)
    iid = a.instrument_id
    if a.first and view:
        rk = (view.get("ranking") or {}).get("rows") or []
        iid = rk[0]["instrument_id"] if rk else next(
            (o["instrument_id"] for o in view.get("opportunities", [])), None)
    t = trace.candidate_trace(view, iid or "", health_service.read_rollout(data_dir))
    if t is None:
        print(f"«{iid}» no está en la última vista publicada del escáner")
        return 5
    if a.json:
        print(json.dumps(t, ensure_ascii=False, indent=1))
    else:
        print(f"{t['symbol']} ({t['asset_class']}, {t['timeframe']}) · traza {t['trace_id']}")
        for k, s in enumerate(t["steps"], 1):
            print(f"  {k}. {s['title']} [{s['status']}]: {s['summary']}")
    if a.summary:
        last = t["steps"][-1]
        Path(a.summary).write_text(
            f"recorrido de {t['symbol']} ({t['trace_id']}): {len(t['steps'])} pasos, del dato "
            f"({t['steps'][0]['summary']}) a la decisión ({last['summary']})", encoding="utf-8")
    return 0


def add_parsers(sub) -> None:
    h = sub.add_parser("health", help="revisión de salud multiactivo (T102)")
    h.add_argument("--json", action="store_true")
    h.add_argument("--summary", help="archivo con una línea de resumen (para el plan)")
    h.add_argument("--quiet", action="store_true", help="sin globo ni registro de avisos")
    t = sub.add_parser("trace", help="recorrido de una candidata, del dato a la decisión (T102)")
    t.add_argument("instrument_id", nargs="?")
    t.add_argument("--first", action="store_true", help="la primera candidata del ranking")
    t.add_argument("--json", action="store_true")
    t.add_argument("--summary", help="archivo con una línea de resumen (para el plan)")
