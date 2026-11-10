"""Descubrir → catalogar → puntuar → encolar (T64). Orquesta el I/O; la decisión es pura
(`eim.video.relevance`).

Descargar NO es parte de esto: la cola solo dice qué procesar y en qué orden, y T65 solo puede
tomar videos con permiso de transcripción (T62).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from eim.data.video.catalog import VideoCatalog
from eim.data.video.discover import QuotaGuard, YouTubeApi, discover, recheck
from eim.video.models import VideoMeta
from eim.video.relevance import Candidate, Mode, admit, score
from eim.video.watchlist import Watchlist

RECHECK_DAYS = 14   # se comprueba si siguen existiendo los videos publicados en estos días
RETRY = {"tope_diario", "en_vivo", "sin_duracion", "borrado"}   # descartes que se reconsideran


def catalog_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "video.duckdb"


def utc_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def quota_guard(cat: VideoCatalog, wl: Watchlist, now: int) -> QuotaGuard:
    day = utc_day(now)
    return QuotaGuard(wl.budget.quota_units_per_day, lambda: cat.quota_used(day),
                      lambda n: cat.quota_add(day, n))


def sources(cat: VideoCatalog, wl: Watchlist, now: int, client: httpx.Client | None = None,
            ) -> tuple[YouTubeApi | None, httpx.Client | None]:
    api = YouTubeApi.from_env(quota_guard(cat, wl, now), client=client)
    rss = (client or httpx.Client(timeout=20.0)) if wl.rss_enabled and api is None else None
    return api, rss


def run_discover(cat: VideoCatalog, wl: Watchlist, now: int, api: YouTubeApi | None,
                 rss: httpx.Client | None, *, channels: list[str] | None = None,
                 since_ms: int | None = None, kind: str = "discover",
                 mode: Mode = "vivo") -> dict:
    """Una pasada: catálogo al día, borrados detectados (con API) y cola puntuada."""
    ids = channels or [c.channel_id for c in wl.channels]
    pages = wl.budget.backfill_max_pages if kind == "backfill" else wl.budget.max_pages_per_channel
    results = discover(ids, api, rss, max_pages=pages, since_ms=since_ms)
    per_channel, seen = [], []
    for r in results:
        ch = wl.channel(r.channel_id)
        if ch is not None:
            cat.record_channel(ch.channel_id, now, ch.name, r.title, ch.priority, ch.permission,
                               wl.version, wl.hash)
        counts = cat.record_videos(r.metas, now, wl.version, wl.hash) if r.ok else {}
        cat.record_fetch(r.channel_id, now, r.source, kind, r.ok, len(r.metas), r.units,
                         r.error, since_ms)
        seen += [m.video_id for m in r.metas]
        per_channel.append({"channel_id": r.channel_id, "ok": r.ok, "videos": len(r.metas),
                            "units": r.units, "error": r.error, **counts})
    deleted = 0
    if api is not None and kind == "discover":
        recent = [v for v in cat.active_ids(now - RECHECK_DAYS * 86_400_000) if v not in seen]
        alive = recheck(api, recent) if recent else set()
        if alive is not None:
            gone = [v for v in recent if v not in alive]
            deleted = cat.mark_deleted(gone, now, wl.version, wl.hash)
            for vid in gone:   # un borrado no se procesa; si vuelve, se puntúa de nuevo
                q = cat.queue_get(vid)
                if q is not None and q["state"] == "pendiente":
                    cat.queue_transition(vid, "descartado", now, "borrado")
    queued = score_and_queue(cat, wl, now, mode)
    return {"at": now, "kind": kind, "channels": per_channel, "deleted": deleted,
            "queue": queued, "quota_used_today": cat.quota_used(utc_day(now)),
            "quota_limit": wl.budget.quota_units_per_day}


def _meta(v: dict) -> VideoMeta:
    return VideoMeta(video_id=v["video_id"], channel_id=v["channel_id"], title=v["title"],
                     description=v["description"] or "", published_at=v["published_at"],
                     duration_s=v["duration_s"], language=v["language"], live=v["live"],
                     source=v["source"])


def score_and_queue(cat: VideoCatalog, wl: Watchlist, now: int, mode: Mode = "vivo") -> dict:
    """Puntúa lo visible a `now` que no esté admitido y reparte el tope diario.
    Se reconsideran los descartados por tope, en vivo, sin duración o borrados (pueden cambiar
    de una pasada a otra) y todos los puntuados con otra versión de la lista."""
    day = utc_day(now)
    todo, cands = {}, []
    for v in cat.videos_asof(now):
        q = cat.queue_get(v["video_id"])
        if q is not None and (q["state"] != "descartado" or q["wl_hash"] == wl.hash and not (
                set(q["reasons"]) & RETRY)):
            continue
        m = mode if q is None else q["mode"]
        s = score(_meta(v), wl, now, m)
        todo[v["video_id"]] = s
        if s.candidate:
            cands.append(Candidate(v["video_id"], s.total, v["published_at"], s.est_compute_s))
    inside, outside = admit(cands, cat.used_compute_s(day), wl)
    counts = {"pendiente": 0, "descartado": 0}
    for vid, s in todo.items():
        bd = s.breakdown | {"notes": list(s.notes)}
        if vid in inside:
            cat.queue_put(vid, "pendiente", [], s.total, bd, s.est_compute_s, s.mode, day, now,
                          wl.version, wl.hash)
            counts["pendiente"] += 1
        else:
            reasons = list(s.reasons) or (["tope_diario"] if vid in outside else ["bajo_umbral"])
            cat.queue_put(vid, "descartado", reasons, s.total, bd, s.est_compute_s, s.mode,
                          None, now, wl.version, wl.hash)
            counts["descartado"] += 1
    return counts | {"compute_used_s": round(cat.used_compute_s(day), 1),
                     "compute_cap_s": wl.budget.compute_hours_per_day * 3600}
