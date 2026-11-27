"""Tabla `video_observations` (T66), solo-añadir, en `data/video/visual.duckdb` (fuera de git).

Base propia y no `data/video.duckdb`: el servicio de vigilancia de T64 (`EIM_VIDEO=1`) mantiene
abierta la del catálogo y DuckDB no admite dos procesos escribiendo el mismo archivo.
Cada fila es una `VisualObservation` más la hora de registro; nada se actualiza ni se borra. Una
nueva lectura del mismo fotograma (otra versión de parámetros o de motor) son filas nuevas: la
clave lógica es `(frame_id, params_version, engine, kind, value, unit)` y se ignoran repetidas.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import duckdb

from eim.core.video import VisualObservation
from eim.data.duck import tune

_COLS = ("video_id", "t", "frame_id", "kind", "value_num", "value_text", "unit", "box", "quote",
         "source", "validation", "validation_note", "symbol", "timeframe", "confidence",
         "engine", "model", "weights_sha", "params_version", "recorded_at")
_DDL = """
CREATE TABLE IF NOT EXISTS video_observations (
    video_id VARCHAR, t DOUBLE, frame_id VARCHAR, kind VARCHAR, value_num DOUBLE,
    value_text VARCHAR, unit VARCHAR, box VARCHAR, quote VARCHAR, source VARCHAR,
    validation VARCHAR, validation_note VARCHAR, symbol VARCHAR, timeframe VARCHAR,
    confidence DOUBLE, engine VARCHAR, model VARCHAR, weights_sha VARCHAR,
    params_version VARCHAR, recorded_at BIGINT);
"""
_KEY = ("frame_id", "params_version", "engine", "kind", "value_num", "value_text", "unit")


def observations_path(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("EIM_DATA_DIR", "data")) / "video" / "visual.duckdb"


class ObservationStore:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(self._path)
        tune(self._con)
        self._con.execute(_DDL)
        self._lock = threading.Lock()

    def close(self) -> None:
        self._con.close()

    @staticmethod
    def _row(o: VisualObservation, now: int) -> tuple:
        num = o.value if isinstance(o.value, float) else None
        txt = o.value if isinstance(o.value, str) else None
        return (o.video_id, o.t, o.frame_id, o.kind, num, txt, o.unit,
                json.dumps(o.box) if o.box else None, o.quote, o.source, o.validation,
                o.validation_note, o.symbol, o.timeframe, o.confidence, o.engine, o.model,
                o.weights_sha, o.params_version, now)

    def append(self, obs: list[VisualObservation], now: int | None = None) -> int:
        """Añade las observaciones nuevas (las repetidas por clave lógica se ignoran)."""
        now = int(time.time() * 1000) if now is None else now
        rows = [self._row(o, now) for o in obs]
        idx = [_COLS.index(k) for k in _KEY]
        cond = " AND ".join(f"{k} IS NOT DISTINCT FROM ?" for k in _KEY)
        added = 0
        with self._lock:
            for r in {tuple(r[i] for i in idx): r for r in rows}.values():
                hit = self._con.execute(f"SELECT 1 FROM video_observations WHERE {cond} LIMIT 1",
                                        [r[i] for i in idx]).fetchone()
                if hit:
                    continue
                self._con.execute(f"INSERT INTO video_observations VALUES "
                                  f"({','.join('?' * len(_COLS))})", list(r))
                added += 1
        return added

    def for_video(self, video_id: str, *, accepted_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM video_observations WHERE video_id = ?"
        if accepted_only:
            sql += " AND validation IN ('confirmada', 'plausible')"
        with self._lock:
            rows = self._con.execute(sql + " ORDER BY t, kind", [video_id]).fetchall()
        return [dict(zip(_COLS, r, strict=True)) for r in rows]

    def counts(self) -> list[dict]:
        """Recuento por tipo y estado de validación (para `python -m eim.video.visual stats`)."""
        with self._lock:
            rows = self._con.execute(
                "SELECT kind, validation, count(*) FROM video_observations "
                "GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
        return [{"kind": k, "validation": v, "n": n} for k, v, n in rows]
