"""Registro de salud de los motores locales (T63): tabla `localai_calls`, solo añadir.

Una fila por llamada: motor, modelo, SHA de los pesos, parámetros, latencia, RAM pico, resultado
(`valid` / `repaired` / `invalid` / `timeout` / `down` / `deferred` / `off`) y llamador. El resumen
por motor y modelo (tasa de JSON válido, latencia p50/p90, fallos) es la base de la comparación
de T71 y del panel de T70, y está **separado de cualquier métrica de rentabilidad**: aquí no hay
ni una cifra de P&L.

La base (`EIM_LOCALAI_DB`) se abre solo para escribir cada fila y se cierra: DuckDB admite un
escritor por archivo y los trabajos de motores pueden ser varios procesos en serie. Si otro
proceso la tiene abierta, la fila va a `localai_calls.pending.jsonl` junto a la base y se
incorpora en la siguiente escritura que sí la abra (nunca se pierde ni se reescribe una fila).
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from eim.localai.results import EngineResult

DDL = """CREATE TABLE IF NOT EXISTS localai_calls (
    call_id VARCHAR PRIMARY KEY, started_ms BIGINT, kind VARCHAR, engine_id VARCHAR,
    model VARCHAR, weights_sha VARCHAR, params VARCHAR, input_sha VARCHAR, schema_sha VARCHAR,
    latency_s DOUBLE, ram_peak_mb DOUBLE, outcome VARCHAR, status VARCHAR, reason VARCHAR,
    caller VARCHAR, attempts INTEGER)"""
COLS = ("call_id", "started_ms", "kind", "engine_id", "model", "weights_sha", "params",
        "input_sha", "schema_sha", "latency_s", "ram_peak_mb", "outcome", "status", "reason",
        "caller", "attempts")


def row_of(res: EngineResult) -> dict[str, Any]:
    p = res.provenance
    return {"call_id": uuid.uuid4().hex, "started_ms": p.started_ms, "kind": p.kind,
            "engine_id": p.engine_id, "model": p.model, "weights_sha": p.weights_sha,
            "params": json.dumps(p.params, sort_keys=True, ensure_ascii=False, default=str),
            "input_sha": p.input_sha, "schema_sha": p.schema_sha,
            "latency_s": round(p.elapsed_s, 4), "ram_peak_mb": p.ram_peak_mb,
            "outcome": res.outcome, "status": res.status, "reason": res.reason[:500],
            "caller": p.caller, "attempts": p.attempts}


class HealthLog:
    """`record(result)` nunca lanza: registrar la salud no puede tumbar al llamador."""

    def __init__(self, path: str | Path | None) -> None:
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self.memory: list[dict[str, Any]] = []   # sin base (tests, `EIM_LOCALAI_DB` vacío)

    @property
    def spool(self) -> Path | None:
        return self.path.with_name("localai_calls.pending.jsonl") if self.path else None

    def _connect(self):
        import duckdb

        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(self.path))
        con.execute(DDL)
        return con

    def _insert(self, con, rows: list[dict[str, Any]]) -> None:
        con.executemany(
            f"INSERT INTO localai_calls ({', '.join(COLS)}) VALUES ({', '.join('?' * len(COLS))})"
            " ON CONFLICT DO NOTHING", [[r[c] for c in COLS] for r in rows])

    def record(self, res: EngineResult) -> None:
        row = row_of(res)
        with self._lock:
            if self.path is None:
                self.memory.append(row)
                return
            try:
                con = self._connect()
            except Exception:  # noqa: BLE001 — base ocupada por otro proceso: a la cola local
                self._to_spool(row)
                return
            try:
                pending = self._drain()
                self._insert(con, [*pending, row])
                if pending and self.spool:
                    self.spool.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                self._to_spool(row)
            finally:
                con.close()

    def _to_spool(self, row: dict[str, Any]) -> None:
        try:
            assert self.spool is not None
            self.spool.parent.mkdir(parents=True, exist_ok=True)
            with self.spool.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except (OSError, AssertionError):
            self.memory.append(row)

    def _drain(self) -> list[dict[str, Any]]:
        if not self.spool or not self.spool.exists():
            return []
        rows = []
        for line in self.spool.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows

    # --- lectura -------------------------------------------------------------------------
    def rows(self) -> list[dict[str, Any]]:
        if self.path is None or not self.path.exists():
            return list(self.memory) + self._drain()
        import duckdb

        try:
            con = duckdb.connect(str(self.path), read_only=True)
        except Exception:  # noqa: BLE001
            return self._drain()
        try:
            got = con.execute(f"SELECT {', '.join(COLS)} FROM localai_calls "
                              "ORDER BY started_ms").fetchall()
        finally:
            con.close()
        return [dict(zip(COLS, r, strict=True)) for r in got] + self._drain()


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))], 3)


def summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Salud por (etapa, motor, modelo): llamadas, tasa de JSON válido (válido + reparado sobre
    las que llegaron a responder), latencia p50/p90 de las respondidas y fallos por tipo. Sin
    métricas de rentabilidad."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["kind"], r["engine_id"], r["model"]), []).append(r)
    out = []
    for (kind, engine, model), rs in sorted(groups.items()):
        n = {k: sum(1 for r in rs if r["outcome"] == k) for k in
             ("valid", "repaired", "invalid", "timeout", "down", "deferred", "off")}
        answered = n["valid"] + n["repaired"] + n["invalid"]
        lat = [r["latency_s"] for r in rs if r["outcome"] in {"valid", "repaired", "invalid"}]
        peaks = [r["ram_peak_mb"] for r in rs if r["ram_peak_mb"] is not None]
        out.append({
            "kind": kind, "engine_id": engine, "model": model, "calls": len(rs),
            "valid_rate": round((n["valid"] + n["repaired"]) / answered, 4) if answered else None,
            "repaired_rate": round(n["repaired"] / answered, 4) if answered else None,
            "latency_p50_s": _pct(lat, 0.5), "latency_p90_s": _pct(lat, 0.9),
            "ram_peak_max_mb": max(peaks) if peaks else None,
            "weights_sha": sorted({r["weights_sha"] for r in rs if r["weights_sha"]}),
            **{f"n_{k}": v for k, v in n.items()},
        })
    return out
