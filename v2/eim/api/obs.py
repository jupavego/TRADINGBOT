"""API de SOLO LECTURA del observatorio (T73): `/v2/obs/*`. Ningún POST/PUT/DELETE.

Cada respuesta declara `source`, `asof` y cuánto se retrasa el propio observatorio (antigüedad
del último evento indexado y retraso del indexador): el retraso se muestra, no se esconde.
Los datos son un DERIVADO de los JSONL (`data/obs/spool/`); si `obs.duckdb` se pierde, se
reconstruye indexando de nuevo lo que quede en el spool.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from eim.api.reports_db import ReportStore
from eim.observability import catalog
from eim.observability import thresholds as T
from eim.observability.bridge import alerts_bridge, heartbeat_bridge, risk_bridge
from eim.observability.derive import stage_rank
from eim.observability.indexer import Indexer
from eim.observability.store import ObsStore

SOURCE = "obs.duckdb (derivado de data/obs/spool; no viaja entre equipos)"
_ID = re.compile(r"^[A-Za-z0-9_.:|\-]{1,120}$")
Page = Query(T.PAGE_MAX // 5, ge=1, le=T.PAGE_MAX)


def build_observatory(data_dir: Path, reports: ReportStore) -> tuple[ObsStore, Indexer, dict]:
    """Almacén + indexador único + puentes de solo lectura (latidos, alertas, riesgo), y las
    bases que entran en la copia de seguridad. Lo arranca la API (`Indexer.loop`)."""
    store = ObsStore(data_dir / "obs" / "obs.duckdb")
    con, lock = reports.connection
    indexer = Indexer(store, data_dir / "obs" / "spool", bridges=(
        ("heartbeat", heartbeat_bridge(data_dir)), ("alerts", alerts_bridge(con, lock)),
        ("risk", risk_bridge(con, lock))))
    return store, indexer, {"obs.duckdb": (store.con, store.lock)}


def _check_id(value: str | None, what: str) -> None:
    if value is not None and not _ID.match(value):
        raise HTTPException(400, f"{what} no válido")


def _where(conds: list[tuple[str, Any]]) -> tuple[str, list]:
    use = [(c, v) for c, v in conds if v is not None]
    return (" WHERE " + " AND ".join(c for c, _ in use)) if use else "", [v for _, v in use]


def build_obs_router(store: ObsStore, indexer: Indexer,
                     reports_conn: tuple[Any, threading.Lock] | None = None) -> APIRouter:
    r = APIRouter(prefix="/v2/obs", tags=["observatorio"])

    def envelope(**body: Any) -> dict:
        now = int(time.time() * 1000)
        last = store.scalar("SELECT max(ts_utc) FROM events")
        lag = (None if indexer.last_pass_ms is None
               else round((now - indexer.last_pass_ms) / 1000, 1))
        return {"source": SOURCE, "asof": now, "last_event_ms": last,
                "last_event_age_s": None if last is None else round((now - last) / 1000, 1),
                "index_lag_s": lag, **body}

    def page(table: str, cols: str, conds: list, order: str, limit: int, offset: int):
        where, args = _where(conds)
        total = store.scalar(f"SELECT count(*) FROM {table}{where}", args)
        rows = store.query(f"SELECT {cols} FROM {table}{where} ORDER BY {order} "
                           f"LIMIT {int(limit)} OFFSET {int(offset)}", args)
        return rows, total

    def with_refs(rows: list[dict]) -> list[dict]:
        ids = [x["event_id"] for x in rows]
        refs: dict[str, dict[str, list]] = {}
        for i in range(0, len(ids), 1000):
            part = ids[i:i + 1000]
            for f in store.query(
                    "SELECT event_id, direction, ordinal, type, id, hash, params_version FROM refs"
                    f" WHERE event_id IN ({','.join('?' * len(part))}) ORDER BY ordinal", part):
                refs.setdefault(f["event_id"], {"in": [], "out": []})[f["direction"]].append(
                    {k: f[k] for k in ("type", "id", "hash", "params_version")})
        for x in rows:
            x["detail"] = json.loads(x["detail"]) if x.get("detail") else {}
            x["inputs"] = refs.get(x["event_id"], {}).get("in", [])
            x["outputs"] = refs.get(x["event_id"], {}).get("out", [])
        return rows

    @r.get("/components")
    def components(stage: str | None = None, layer: str | None = None,
                   built: str | None = None) -> dict:
        last = {x["component_id"]: x for x in store.query(
            "SELECT component_id, max(ts_utc) AS last_ms, arg_max(status, ts_utc) AS last_status,"
            " count(*) AS n_events FROM events GROUP BY component_id")}
        now = int(time.time() * 1000)
        items = []
        for c in catalog.COMPONENTS:
            if (stage and c.stage != stage) or (layer and c.layer != layer) \
                    or (built and c.built != built):
                continue
            seen = last.get(c.id)
            age = None if seen is None else round((now - seen["last_ms"]) / 1000, 1)
            limit_s = T.stale_after_s(c.cadence_s)
            items.append({
                **c.model_dump(mode="json"), "last_event_ms": seen and seen["last_ms"],
                "last_status": seen and seen["last_status"], "n_events": seen["n_events"] if seen
                else 0, "age_s": age, "stale_after_s": limit_s,
                "no_data": c.built == "construido" and (
                    seen is None or (limit_s is not None and age is not None and age > limit_s))})
        return envelope(items=items, total=len(items), stages=list(catalog.STAGES))

    @r.get("/graph")
    def graph() -> dict:
        stats = {x["component_id"]: x for x in store.query(
            "SELECT component_id, max(ts_utc) AS last_ms, count(*) AS n FROM events "
            "GROUP BY component_id")}
        nodes = [{"id": c.id, "stage": c.stage, "kind": c.kind, "built": c.built,
                  "title_es": c.title_es, "last_event_ms": (stats.get(c.id) or {}).get("last_ms"),
                  "n_events": (stats.get(c.id) or {}).get("n", 0)} for c in catalog.COMPONENTS]
        edges = [{"source": s, "target": t, "artifact": a} for s, t, a in catalog.edges()]
        return envelope(nodes=nodes, edges=edges, stages=list(catalog.STAGES),
                        stage_titles_es=catalog.STAGE_TITLES_ES)

    @r.get("/runs")
    def runs(component_id: str | None = None, status: str | None = None,
             trace_id: str | None = None, since: int | None = None, until: int | None = None,
             limit: int = Page, offset: int = Query(0, ge=0)) -> dict:
        _check_id(trace_id, "trace_id")
        rows, total = page("runs", "*", [
            ("component_id = ?", component_id), ("status = ?", status),
            ("trace_id = ?", trace_id), ("started_ms >= ?", since), ("started_ms < ?", until)],
            "started_ms DESC NULLS LAST, run_id", limit, offset)
        return envelope(items=rows, total=total, limit=limit, offset=offset)

    @r.get("/events")
    def events(component_id: str | None = None, kind: str | None = None,
               status: str | None = None, process: str | None = None,
               trace_id: str | None = None, run_id: str | None = None,
               since: int | None = None, until: int | None = None,
               limit: int = Page, offset: int = Query(0, ge=0)) -> dict:
        _check_id(trace_id, "trace_id")
        _check_id(run_id, "run_id")
        rows, total = page("events", "*", [
            ("component_id = ?", component_id), ("kind = ?", kind), ("status = ?", status),
            ("process = ?", process), ("trace_id = ?", trace_id), ("run_id = ?", run_id),
            ("ts_utc >= ?", since), ("ts_utc < ?", until)],
            "ts_utc DESC, event_id DESC", limit, offset)
        return envelope(items=with_refs(rows), total=total, limit=limit, offset=offset)

    @r.get("/traces")
    def traces(symbol: str | None = None, timeframe: str | None = None,
               outcome: str | None = None, has_error: bool | None = None,
               since: int | None = None, until: int | None = None,
               limit: int = Page, offset: int = Query(0, ge=0)) -> dict:
        rows, total = page("decisions", "*", [
            ("symbol = ?", symbol), ("timeframe = ?", timeframe), ("outcome = ?", outcome),
            ("has_error = ?", has_error), ("last_ms >= ?", since), ("last_ms < ?", until)],
            "last_ms DESC, trace_id", limit, offset)
        for x in rows:
            x["links"] = json.loads(x["links"] or "{}")
        return envelope(items=rows, total=total, limit=limit, offset=offset)

    @r.get("/traces/{trace_id}")
    def trace(trace_id: str) -> dict:
        _check_id(trace_id, "trace_id")
        dec = store.query("SELECT * FROM decisions WHERE trace_id = ?", [trace_id])
        evs = store.query("SELECT * FROM events WHERE trace_id = ?", [trace_id])
        if not dec and not evs:
            raise HTTPException(404, f"sin traza {trace_id} (¿purgada o aún sin indexar?)")
        evs.sort(key=lambda e: (e["ts_utc"], e["kind"] != "run_start",
                                stage_rank(e["component_id"]), e["event_id"]))
        links = json.loads(dec[0]["links"] or "{}") if dec else {}
        if dec:
            dec[0]["links"] = links
        return envelope(
            decision=dec[0] if dec else None, events=with_refs(evs),
            runs=store.query("SELECT * FROM runs WHERE trace_id = ? ORDER BY started_ms, run_id",
                             [trace_id]),
            resolved=_resolve(reports_conn, links),
            partial=bool(dec) and not evs)   # eventos crudos ya purgados: queda el resumen

    @r.get("/health")
    def health() -> dict:
        st = indexer.status()
        return envelope(ok=st.pop("ok"), problems=st.pop("problems"), **st,
                        thresholds={"index_lag_s_max": T.INDEX_LAG_S_MAX,
                                    "spool_alert_mb": T.SPOOL_ALERT_MB,
                                    "event_retention_days": T.EVENT_RETENTION_DAYS,
                                    "run_retention_days": T.RUN_RETENTION_DAYS})

    return r


def _resolve(conn: tuple[Any, threading.Lock] | None, links: dict) -> dict[str, list[dict]]:
    """Comprueba (solo lectura) que las referencias existen en los libros de origen. No copia
    su contenido: devuelve `found` y los campos mínimos para enlazar a la vista que corresponda."""
    out: dict[str, list[dict]] = {}
    if conn is None:
        return out
    con, lock = conn
    queries = {
        "risk_decision": "SELECT id, symbol, timeframe, approved, decided_at FROM risk_decisions"
                         " WHERE id = ?",
        "sim_trade": "SELECT id, symbol, timeframe, status, entry_t FROM sim_trades WHERE id = ?",
    }
    for typ, sql in queries.items():
        for ref in links.get(typ, [])[:50]:
            try:
                with lock:
                    row = con.execute(sql, [ref]).fetchone()
            except Exception:  # noqa: BLE001 - tabla ausente en este equipo
                row = None
            names = ("id", "symbol", "timeframe", "state", "t")
            out.setdefault(typ, []).append(
                {"ref": ref, "found": row is not None, **(dict(zip(names, row, strict=True))
                                                          if row else {})})
    for ref in links.get("agent_report", [])[:50]:      # id: símbolo|marco|agente|versión|asof
        parts = ref.split("|")
        found = False
        if len(parts) == 5 and parts[4].isdigit():
            try:
                with lock:
                    found = con.execute(
                        "SELECT 1 FROM reports WHERE symbol=? AND timeframe=? AND agent_id=? "
                        "AND version=? AND asof_ms=?", [*parts[:4], int(parts[4])]
                    ).fetchone() is not None
            except Exception:  # noqa: BLE001
                found = False
        out.setdefault("agent_report", []).append({"ref": ref, "found": found})
    return out
