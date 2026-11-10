"""Servicio de vigilancia de video (T64): una pasada cada `every_s` y latido propio.

Opcional: `servicio_continuo.ps1` solo lo lanza con `EIM_VIDEO=1`. Instancia única
(`data/video/service.lock`). El catálogo se abre solo durante cada pasada: DuckDB admite un único
proceso escritor y así la CLI (`list`, `show`…) puede leerlo entre pasadas.
Latido en `data/video/heartbeat.json`: estado, última pasada, canales ok/fallidos y cuota.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from eim.data.video.catalog import VideoCatalog
from eim.data.video.pipeline import catalog_path, run_discover, sources
from eim.operation.origin import stamp
from eim.operation.priority import apply_role
from eim.operation.watchdog import instance_lock
from eim.video.watchlist import Watchlist

log = logging.getLogger("eim.video")
HEARTBEAT = "heartbeat.json"
BEAT_EVERY_S = 60


def write_heartbeat(directory: Path, row: dict) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        tmp = directory / (HEARTBEAT + ".tmp")
        tmp.write_text(json.dumps(stamp(row), ensure_ascii=False), encoding="utf-8")
        tmp.replace(directory / HEARTBEAT)
    except OSError as exc:   # un disco lleno no detiene el servicio
        log.error("latido: %s", exc)


def one_pass(data_dir: Path, wl: Watchlist, now: int) -> dict:
    cat = VideoCatalog(catalog_path(data_dir))
    try:
        api, rss = sources(cat, wl, now)
        if api is None and rss is None:
            return {"state": "sin_fuente", "error": "falta EIM_YOUTUBE_API_KEY"}
        res = run_discover(cat, wl, now, api, rss)
    finally:
        cat.close()
    ok = sum(c["ok"] for c in res["channels"])
    return {"state": "ok" if ok == len(res["channels"]) else ("degradado" if ok else "caido"),
            "channels_ok": ok, "channels": len(res["channels"]),
            "errors": [c["error"] for c in res["channels"] if c["error"]][:5],
            "queue": res["queue"], "deleted": res["deleted"],
            "quota_used_today": res["quota_used_today"], "quota_limit": res["quota_limit"]}


def serve(data_dir: Path, wl: Watchlist, *, every_s: float, once: bool = False,
          clock=time.time, sleep=time.sleep) -> int:
    vdir = data_dir / "video"
    lock = instance_lock(vdir / "service.lock")
    if lock is None:
        print("El servicio de video ya corre: no se lanza otro.")
        return 0
    if not once:
        apply_role("video")   # T126: prioridad baja (batch), es prescindible
    last: dict = {"state": "arrancando"}
    try:
        while True:
            started = clock()
            try:
                last = one_pass(data_dir, wl, int(started * 1000)) | {
                    "last_pass": int(started * 1000)}
            except Exception as exc:   # noqa: BLE001 — una pasada rota no tumba el servicio
                log.exception("pasada de video")
                last = {"state": "error", "error": f"{type(exc).__name__}: {exc}"[:300],
                        "last_pass": int(started * 1000)}
            row = {"last_heartbeat": clock(), "pid": os.getpid(), "watchlist": wl.version,
                   "every_s": every_s, **last}
            write_heartbeat(vdir, row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if once:
                return 0 if last["state"] in ("ok", "degradado") else 1
            while clock() - started < every_s:
                sleep(min(BEAT_EVERY_S, max(0.0, every_s - (clock() - started))))
                write_heartbeat(vdir, row | {"last_heartbeat": clock()})
    finally:
        lock.close()
