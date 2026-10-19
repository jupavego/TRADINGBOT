"""Puente de solo lectura con lo que ya existe (T73): latidos, alertas y decisiones de riesgo
se presentan como eventos del catálogo SIN tocar esos módulos.

Cada adaptador devuelve `(eventos, marca_de_agua)`; los `event_id` son deterministas, así que
releer lo mismo no duplica. Solo lee: `heartbeat.json` y las tablas `op_alerts` y
`risk_decisions` (por la conexión y el cerrojo de la API).
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb

from eim.core.mode import Mode
from eim.observability.events import ObsEvent, Ref, trace_for

HEARTBEATS = (            # (carpeta bajo data/, componente del catálogo, proceso)
    ("operation", "operation.supervisor", "operation"),
    ("paper", "paper.broker", "api"),
    ("leaders", "leaders.service", "leaders"),
)
_LEVEL_STATUS = {"critical": "error", "warn": "degraded", "info": "ok"}
BATCH = 5000


def _eid(prefix: str, *parts: Any) -> str:
    h = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{h}"


def _ms(v: Any) -> int | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return int(x * 1000) if 0 < x < 1e11 else int(x) if x > 0 else None


def _mode(value: Any) -> Mode:
    try:
        return Mode(str(value).upper())
    except ValueError:
        return Mode.ANALISIS


def heartbeat_bridge(data_dir: Path) -> Callable[[int], tuple[list[ObsEvent], int]]:
    """Un evento `heartbeat` por latido nuevo (el archivo solo guarda el último)."""
    def run(mark: int) -> tuple[list[ObsEvent], int]:
        out: list[ObsEvent] = []
        newest = mark
        for sub, comp, proc in HEARTBEATS:
            p = data_dir / sub / "heartbeat.json"
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                ts = (_ms(raw.get("last_heartbeat")) or _ms(raw.get("last_tick"))
                      or int(p.stat().st_mtime * 1000))
            except (OSError, ValueError, AttributeError):
                continue
            if ts <= 0:
                continue
            err = raw.get("error")
            out.append(ObsEvent(
                event_id=_eid("hb", sub, ts), ts_utc=ts, process=proc, component_id=comp,
                kind="heartbeat", status="degraded" if err else "ok", run_id=f"hb-{sub}",
                mode=_mode(raw.get("mode")), source=f"data/{sub}/heartbeat.json",
                detail={k: raw[k] for k in ("state", "cycles", "consecutive_failures", "saved",
                                            "pid", "error") if k in raw}))
            newest = max(newest, ts)
        return out, newest
    return run


def alerts_bridge(con: duckdb.DuckDBPyConnection,
                  lock: threading.Lock) -> Callable[[int], tuple[list[ObsEvent], int]]:
    """`op_alerts` → eventos `alert` del componente `operation.alerts`."""
    def run(mark: int) -> tuple[list[ObsEvent], int]:
        try:
            with lock:
                rows = con.execute(
                    "SELECT t, kind, level, key, alert FROM op_alerts WHERE t >= ? "
                    f"ORDER BY t LIMIT {BATCH}", [mark]).fetchall()
        except duckdb.CatalogException:     # la tabla aún no existe (servicio sin arrancar)
            return [], mark
        out = []
        for t, kind, level, key, alert in rows:
            try:
                a = json.loads(alert)
            except (TypeError, ValueError):
                a = {}
            out.append(ObsEvent(
                event_id=_eid("al", t, kind, key, alert), ts_utc=int(t), process="api",
                component_id="operation.alerts", kind="alert",
                status=_LEVEL_STATUS.get(level, "degraded"), run_id=f"al-{kind}",
                source="op_alerts",
                detail={"alert_kind": kind, "level": level, "key": key,
                        "title": a.get("title"), "resolved": a.get("resolved", False)}))
        return out, int(rows[-1][0]) if rows else mark
    return run


def risk_bridge(con: duckdb.DuckDBPyConnection,
                lock: threading.Lock) -> Callable[[int], tuple[list[ObsEvent], int]]:
    """`risk_decisions` → eventos `risk_decision`, con la traza de su vela. Un resultado
    distinto del mismo plan es otro evento (el id de la decisión ya lo distingue)."""
    def run(mark: int) -> tuple[list[ObsEvent], int]:
        try:
            with lock:
                rows = con.execute(
                    "SELECT id, symbol, timeframe, plan_id, asof_ms, decided_at, approved, "
                    "decision FROM risk_decisions WHERE decided_at >= ? "
                    f"ORDER BY decided_at LIMIT {BATCH}", [mark]).fetchall()
        except duckdb.CatalogException:
            return [], mark
        out = []
        for did, sym, tf, plan_id, asof, decided, approved, blob in rows:
            try:
                d = json.loads(blob)
            except (TypeError, ValueError):
                d = {}
            out.append(ObsEvent(
                event_id=_eid("rk", did), ts_utc=int(decided), process="api",
                component_id="risk.engine", kind="risk_decision",
                status="ok" if approved else "rejected", run_id=f"rk-{plan_id}",
                trace_id=trace_for(sym, tf, int(asof)), mode=_mode(d.get("mode")),
                source="risk_decisions", inputs=(Ref(type="plan", id=str(plan_id)),),
                outputs=(Ref(type="risk_decision", id=str(did)),),
                detail={"symbol": sym, "timeframe": tf, "approved": bool(approved),
                        "size": d.get("size"), "reasons": list(d.get("reasons") or [])[:4],
                        "config_version": d.get("config_version")}))
        return out, int(rows[-1][5]) if rows else mark
    return run
