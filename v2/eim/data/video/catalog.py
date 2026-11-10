"""Catálogo de video (T64) en `data/video.duckdb` (fuera de git).

- `videos`: point-in-time y solo-añadir. Clave lógica = id de video; cada cambio (título editado,
  borrado, re-publicación) es una fila nueva con su `seen_at`. `first_seen_at` = primer
  `seen_at`: **antes de esa marca el video no existe para el sistema**.
- `video_channels`: cada cambio de un canal (nombre, prioridad, permiso, versión de la lista).
- `video_queue`: estado operativo, una fila por video (pendiente/en_curso/hecho/fallido/
  descartado con motivos). No se reabre lo ya admitido al volver a puntuar.
- `video_fetches` y `video_quota`: cada consulta por canal (cobertura real) y el gasto diario
  de la Data API v3.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import duckdb

from eim.data.duck import tune
from eim.video.models import VideoMeta

STATES = ("pendiente", "en_curso", "hecho", "fallido", "descartado")
LOCKED = ("pendiente", "en_curso", "hecho", "fallido")   # rescorar no los toca
_V = ("video_id, seen_at, channel_id, published_at, title, description, duration_s, language, "
      "live, source, deleted, wl_version, wl_hash")
_DDL = """
CREATE TABLE IF NOT EXISTS videos (
    video_id VARCHAR, seen_at BIGINT, channel_id VARCHAR, published_at BIGINT, title VARCHAR,
    description VARCHAR, duration_s INTEGER, language VARCHAR, live VARCHAR, source VARCHAR,
    deleted BOOLEAN, wl_version VARCHAR, wl_hash VARCHAR, PRIMARY KEY (video_id, seen_at));
CREATE TABLE IF NOT EXISTS video_channels (
    channel_id VARCHAR, seen_at BIGINT, name VARCHAR, title VARCHAR, priority INTEGER,
    permission VARCHAR, wl_version VARCHAR, wl_hash VARCHAR, PRIMARY KEY (channel_id, seen_at));
CREATE TABLE IF NOT EXISTS video_queue (
    video_id VARCHAR PRIMARY KEY, state VARCHAR, reasons VARCHAR, score DOUBLE,
    breakdown VARCHAR, est_compute_s DOUBLE, mode VARCHAR, admitted_day VARCHAR,
    created_at BIGINT, updated_at BIGINT, wl_version VARCHAR, wl_hash VARCHAR);
CREATE TABLE IF NOT EXISTS video_fetches (
    channel_id VARCHAR, fetched_at BIGINT, source VARCHAR, kind VARCHAR, ok BOOLEAN, n BIGINT,
    units BIGINT, error VARCHAR, since_ms BIGINT);
CREATE TABLE IF NOT EXISTS video_quota (day VARCHAR PRIMARY KEY, units BIGINT);
"""
_LATEST = f"""
SELECT {_V}, first_seen_at FROM (
  SELECT *, min(seen_at) OVER (PARTITION BY video_id) AS first_seen_at,
         row_number() OVER (PARTITION BY video_id ORDER BY seen_at DESC) AS rn
  FROM videos WHERE seen_at <= ?) WHERE rn = 1
"""


class VideoCatalog:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(self._path)
        tune(self._con)
        self._con.execute(_DDL)
        self._lock = threading.Lock()

    def _q(self, sql: str, params: list | tuple = ()) -> list[tuple]:
        with self._lock:
            return self._con.execute(sql, list(params)).fetchall()

    # --- canales ----------------------------------------------------------
    def record_channel(self, channel_id: str, seen_at: int, name: str, title: str | None,
                       priority: int, permission: str, wl_version: str, wl_hash: str) -> bool:
        row = (name, title, priority, permission, wl_version, wl_hash)
        last = self._q("SELECT name, title, priority, permission, wl_version, wl_hash FROM "
                       "video_channels WHERE channel_id = ? ORDER BY seen_at DESC LIMIT 1",
                       [channel_id])
        if last and tuple(last[0]) == row:
            return False
        self._q("INSERT INTO video_channels VALUES (?,?,?,?,?,?,?,?)",
                [channel_id, seen_at, *row])
        return True

    # --- videos -----------------------------------------------------------
    def _latest_rows(self, ids: list[str]) -> dict[str, tuple]:
        if not ids:
            return {}
        rows = self._q(_LATEST.replace("WHERE seen_at <= ?", "WHERE video_id IN "
                                       f"({','.join('?' * len(ids))})"), ids)
        return {r[0]: r for r in rows}

    @staticmethod
    def _key(r: tuple) -> tuple:
        return (r[2], r[4], r[5], r[3], r[6], r[7], r[8], bool(r[10]))

    def record_videos(self, metas: list[VideoMeta], seen_at: int, wl_version: str,
                      wl_hash: str) -> dict[str, int]:
        """Fila nueva solo si es un id nuevo o cambió su contenido (o vuelve tras un borrado)."""
        uniq = {m.video_id: m for m in metas}
        latest = self._latest_rows(list(uniq))
        new_rows, added, changed = [], 0, 0
        for vid, m in uniq.items():
            row = (vid, seen_at, m.channel_id, m.published_at, m.title, m.description,
                   m.duration_s, m.language, m.live, m.source, False, wl_version, wl_hash)
            old = latest.get(vid)
            if old is None:
                added += 1
            elif self._key(old) == self._key(row) or (
                    old[9] == "youtube_api" and m.source == "youtube_rss" and not old[10]):
                continue   # sin cambios (el RSS, más pobre, no pisa a la API)
            else:
                changed += 1
            new_rows.append(row)
        if new_rows:
            with self._lock:
                self._con.executemany(f"INSERT INTO videos VALUES ({','.join('?' * 13)})",
                                      new_rows)
        return {"added": added, "changed": changed, "unchanged": len(uniq) - added - changed}

    def mark_deleted(self, ids: list[str], seen_at: int, wl_version: str, wl_hash: str) -> int:
        rows = [(*r[:1], seen_at, *r[2:10], True, wl_version, wl_hash)
                for r in self._latest_rows(ids).values() if not r[10]]
        if rows:
            with self._lock:
                self._con.executemany(f"INSERT INTO videos VALUES ({','.join('?' * 13)})", rows)
        return len(rows)

    def videos_asof(self, asof: int, channel_id: str | None = None,
                    include_deleted: bool = False) -> list[dict]:
        """Lo que el sistema sabía a `asof`: versión vigente de cada video visto ≤ asof y
        publicado ≤ asof; sin anticipación."""
        sql = f"SELECT * FROM ({_LATEST}) WHERE published_at <= ?"
        params: list = [asof, asof]
        if channel_id:
            sql += " AND channel_id = ?"
            params.append(channel_id)
        if not include_deleted:
            sql += " AND NOT deleted"
        cols = [*(c.strip() for c in _V.split(",")), "first_seen_at"]
        return [dict(zip(cols, r, strict=True))
                for r in self._q(sql + " ORDER BY published_at DESC, video_id", params)]

    def versions(self, video_id: str) -> list[dict]:
        cols = [c.strip() for c in _V.split(",")]
        rows = self._q(f"SELECT {_V} FROM videos WHERE video_id = ? ORDER BY seen_at", [video_id])
        return [dict(zip(cols, r, strict=True)) for r in rows]

    def active_ids(self, since_published: int) -> list[str]:
        return [r[0] for r in self._q(
            f"SELECT video_id FROM ({_LATEST}) WHERE NOT deleted AND published_at >= ?",
            [2**62, since_published])]

    # --- cola -------------------------------------------------------------
    def queue_get(self, video_id: str) -> dict | None:
        rows = self.queue_rows(video_id=video_id)
        return rows[0] if rows else None

    def queue_rows(self, state: str | None = None, video_id: str | None = None) -> list[dict]:
        sql, params = "SELECT * FROM video_queue WHERE 1=1", []
        if state:
            sql, params = sql + " AND state = ?", [*params, state]
        if video_id:
            sql, params = sql + " AND video_id = ?", [*params, video_id]
        cols = ("video_id", "state", "reasons", "score", "breakdown", "est_compute_s", "mode",
                "admitted_day", "created_at", "updated_at", "wl_version", "wl_hash")
        out = []
        for r in self._q(sql + " ORDER BY score DESC NULLS LAST, video_id", params):
            d = dict(zip(cols, r, strict=True))
            d["reasons"] = json.loads(d["reasons"] or "[]")
            d["breakdown"] = json.loads(d["breakdown"] or "{}")
            out.append(d)
        return out

    def queue_put(self, video_id: str, state: str, reasons: list[str], score: float | None,
                  breakdown: dict, est_compute_s: float | None, mode: str,
                  admitted_day: str | None, now: int, wl_version: str, wl_hash: str) -> bool:
        """Alta o actualización; False si el video ya fue admitido (estado bloqueado)."""
        if state not in STATES:
            raise ValueError(f"estado desconocido: {state}")
        old = self.queue_get(video_id)
        if old is not None and old["state"] in LOCKED:
            return False
        created = old["created_at"] if old else now
        self._q("INSERT OR REPLACE INTO video_queue VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [video_id, state, json.dumps(reasons), score,
                 json.dumps(breakdown, ensure_ascii=False, separators=(",", ":")),
                 est_compute_s, mode, admitted_day, created, now, wl_version, wl_hash])
        return True

    def queue_transition(self, video_id: str, state: str, now: int,
                         reason: str | None = None) -> None:
        """Para quien procese la cola (T65): en_curso → hecho/fallido, con motivo."""
        if state not in STATES:
            raise ValueError(f"estado desconocido: {state}")
        self._q("UPDATE video_queue SET state = ?, updated_at = ?, reasons = CASE WHEN ? IS NULL "
                "THEN reasons ELSE to_json([?]) END WHERE video_id = ?",
                [state, now, reason, reason, video_id])

    def used_compute_s(self, day: str) -> float:
        (v,) = self._q("SELECT coalesce(sum(est_compute_s), 0) FROM video_queue "
                       "WHERE admitted_day = ?", [day])[0]
        return float(v)

    # --- consultas a la fuente y cuota --------------------------------------
    def record_fetch(self, channel_id: str, fetched_at: int, source: str, kind: str, ok: bool,
                     n: int, units: int, error: str | None, since_ms: int | None) -> None:
        self._q("INSERT INTO video_fetches VALUES (?,?,?,?,?,?,?,?,?)",
                [channel_id, fetched_at, source, kind, ok, n, units, error, since_ms])

    def quota_used(self, day: str) -> int:
        rows = self._q("SELECT units FROM video_quota WHERE day = ?", [day])
        return int(rows[0][0]) if rows else 0

    def quota_add(self, day: str, units: int) -> None:
        self._q("INSERT INTO video_quota VALUES (?, ?) ON CONFLICT (day) DO UPDATE SET "
                "units = video_quota.units + excluded.units", [day, units])

    def coverage(self) -> list[dict]:
        """Cobertura real por canal: consultas correctas/fallidas y videos vistos."""
        rows = self._q("""
            SELECT f.channel_id, count(*) FILTER (WHERE ok), count(*) FILTER (WHERE NOT ok),
                   min(fetched_at) FILTER (WHERE ok), max(fetched_at) FILTER (WHERE ok),
                   min(since_ms) FILTER (WHERE ok AND kind = 'backfill'),
                   arg_max(error, fetched_at) FILTER (WHERE NOT ok)
            FROM video_fetches f GROUP BY f.channel_id ORDER BY 1""")
        vids = {r[0]: r[1:] for r in self._q(
            f"SELECT channel_id, count(*), min(published_at), max(published_at) "
            f"FROM ({_LATEST}) WHERE NOT deleted GROUP BY 1", [2**62])}
        keys = ("channel_id", "fetch_ok", "fetch_failed", "first_ok", "last_ok",
                "backfill_since", "last_error")
        out = []
        for r in rows:
            d = dict(zip(keys, r, strict=True))
            n, lo, hi = vids.get(r[0], (0, None, None))
            out.append(d | {"videos": n, "published_min": lo, "published_max": hi})
        return out

    def close(self) -> None:
        with self._lock:
            self._con.close()
