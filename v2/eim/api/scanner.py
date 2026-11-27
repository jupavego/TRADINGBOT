"""`GET /v2/scanner/...`: el escáner global en la API (T94). Solo lectura y solo local.

Lee la vista que publica el escáner (`data/scanner/view.json`, `eim/data/scanner_view.py`); nunca
abre `scanner.duckdb` (tiene un solo proceso escritor). No hay ningún POST: nada aquí cambia
estado (si alguno llegara, la regla de `X-EIM-Confirm` de CLAUDE.md seguiría aplicando).
Todas las respuestas llevan el modo (ANÁLISIS) y el aviso «candidata, no validada».

- `/v2/scanner/universe` — último barrido: exclusiones, mercados abiertos/cerrados por clase y
  plaza, y cada instrumento puntuado con su cobertura (filtros `asset_class`, `market`).
- `/v2/scanner/runs` — últimas corridas (barridos, pasadas rápidas y de agentes).
- `/v2/scanner/opportunities` — oportunidades candidatas en el orden del ranking global (T95),
  con el bloque `ranking`: prioridad, umbral del placebo, grupos de apuestas correlacionadas y, por
  candidata, el nº de hipótesis de su familia y su p ajustado (filtros `asset_class`, `market`,
  `side`, `horizon_max_days`).
- `/v2/scanner/instrument/{id}` — detalle: agentes que corrieron y que no (con su motivo),
  síntesis, proyección, avisos y la oportunidad con su trazabilidad.
- `/v2/scanner/health` — T102: salud por clase y por fuente (cobertura, frescura, límites de uso,
  errores, mercados abiertos/cerrados), estado y presupuesto del escáner, qué no se puede ver,
  avisos activos y niveles del despliegue gradual. La frescura se recalcula con la hora de la
  petición: una vista vieja sale «obsoleta» aunque la última revisión la diera por buena.
- `/v2/scanner/trace/{id}` — T102: recorrido de la candidata de un instrumento, del dato a su
  decisión, con la misma traza que sus eventos del observatorio.

Desde T102 las oportunidades de una clase desactivada o apoyadas sobre todo por agentes
desactivados (despliegue gradual, `eim/scanner/rollout.py`) salen aparte, en `shadow`, con su
motivo; `include_shadow=true` las devuelve en la lista.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from eim.data.scanner_view import NOTICE, read_view
from eim.scanner import health, rollout, trace
from eim.scanner.health_service import STATUS_FILE, read_health, read_json, read_rollout

DAY_MS = 86_400_000
EMPTY = {"mode": "ANALISIS", "available": False, "status_label": "candidata, no validada",
         "notice": NOTICE,
         "reason": "El escáner aún no publicó su vista en este equipo: corre `python -m "
                   "eim.scanner sweep --asof latest` y luego `python -m eim.scanner deep` (o el "
                   "servicio `python -m eim.scanner run`)."}


def _head(v: dict) -> dict:
    return {"mode": v["mode"], "available": True, "status_label": v["status_label"],
            "notice": v["notice"], "generated_at": v["generated_at"]}


def _match(x: dict, asset_class: str | None, market: str | None) -> bool:
    return ((asset_class is None or x.get("asset_class") == asset_class)
            and (market is None or x.get("market") == market))


def build_scanner_router(data_dir: Path | Callable[[], Path]) -> APIRouter:
    router = APIRouter(prefix="/v2/scanner")

    def root() -> Path:
        return Path(data_dir() if callable(data_dir) else data_dir)

    def view() -> dict | None:
        return read_view(root())

    @router.get("/universe")
    def get_universe(asset_class: str | None = None, market: str | None = None) -> dict:
        v = view()
        if v is None:
            return dict(EMPTY)
        u = v["universe"]
        rows = [r for r in u["rows"] if _match(r, asset_class, market)]
        return {**_head(v), **{k: u[k] for k in u if k != "rows"}, "rows": rows,
                "deep": v.get("deep")}

    @router.get("/runs")
    def get_runs(limit: int = Query(20, ge=1, le=100)) -> dict:
        v = view()
        if v is None:
            return dict(EMPTY)
        return {**_head(v), "runs": v["runs"][:limit]}

    @router.get("/opportunities")
    def get_opportunities(asset_class: str | None = None, market: str | None = None,
                          side: str | None = None,
                          horizon_max_days: float | None = Query(None, gt=0),
                          include_shadow: bool = False) -> dict:
        v = view()
        if v is None:
            return {**EMPTY, "opportunities": [], "shadow": []}
        out = [o for o in v["opportunities"] if _match(o, asset_class, market)
               and (side is None or o["side"] == side)
               and (horizon_max_days is None or o["horizon_ms"] <= horizon_max_days * DAY_MS)]
        state = read_rollout(root())
        shadow = [{"opportunity_id": o["opportunity_id"], "instrument_id": o["instrument_id"],
                   "symbol": o["symbol"], "reason": why} for o in out
                  if (why := rollout.shadow_reason(o, state))]
        hidden = {x["opportunity_id"] for x in shadow}
        return {**_head(v), "deep": v.get("deep"), "shadow": shadow,
                "opportunities": out if include_shadow else
                [o for o in out if o["opportunity_id"] not in hidden],
                "ranking": v.get("ranking") or {"available": False}}

    @router.get("/health")
    def get_health() -> dict:
        d = root()
        v, saved = view(), read_health(d) or {}
        excl = {c["asset_class"]: c["exclusions"] for c in saved.get("classes", [])
                if c.get("n_excluded") is not None} or None
        h = health.build(v, read_json(d / "scanner" / STATUS_FILE), int(time.time() * 1000),
                         excl_by_class=excl)
        h.update({k: saved.get(k) for k in ("alerts_active", "alerts_recent", "rollout",
                                            "observability")})
        h["checked_at"] = saved.get("generated_at")
        if not saved:
            h["note"] = ("la revisión de salud aún no corrió en este equipo: corre `python -m "
                         "eim.scanner health` (lo hace sola la pasada de agentes)")
        return h

    @router.get("/trace/{instrument_id}")
    def get_trace(instrument_id: str) -> dict:
        v = view()
        if v is None:
            raise HTTPException(404, EMPTY["reason"])
        t = trace.candidate_trace(v, instrument_id, read_rollout(root()))
        if t is None:
            raise HTTPException(404, f"«{instrument_id}» no está en el último barrido publicado")
        return {**_head(v), **t}

    @router.get("/instrument/{instrument_id}")
    def get_instrument(instrument_id: str) -> dict:
        v = view()
        if v is None:
            raise HTTPException(404, EMPTY["reason"])
        d = v["instruments"].get(instrument_id)
        row = next((r for r in v["universe"]["rows"] if r["instrument_id"] == instrument_id),
                   None)
        if d is None and row is None:
            raise HTTPException(404, f"«{instrument_id}» no está en el último barrido publicado")
        opp = next((o for o in v["opportunities"] if o["instrument_id"] == instrument_id), None)
        rank_row = next((r for r in (v.get("ranking") or {}).get("rows", [])
                         if opp and r["opportunity_id"] == opp["opportunity_id"]), None)
        return {**_head(v), "row": row, "deep": d, "opportunity": opp, "rank": rank_row,
                "note": None if d else "fuera de la lista corta: los agentes no corrieron"}

    return router
