"""CLI del catálogo de video (T64). Desde `v2/`:

    python -m eim.video discover [--channel UC…]            una pasada (Data API v3)
    python -m eim.video backfill --channel UC… --since AAAA-MM-DD   pasado, solo catálogo
    python -m eim.video queue [--state pendiente]           cola con tope del día
    python -m eim.video list [--asof AAAA-MM-DDTHH:MM] [--channel UC…]   por qué entró o no
    python -m eim.video show VIDEO_ID                        versiones, puntaje y desglose
    python -m eim.video coverage                             cobertura real por canal
    python -m eim.video run [--every-min 60]                 servicio (lo lanza EIM_VIDEO=1)

Necesita `EIM_YOUTUBE_API_KEY` para descubrir; sin ella todo lo demás funciona sobre lo ya
catalogado. Nada se descarga.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.data.video.catalog import VideoCatalog
from eim.data.video.pipeline import catalog_path, run_discover, sources, utc_day
from eim.video import watchlist as W
from eim.video.relevance import REASONS


def _ms(text: str) -> int:
    dt = datetime.fromisoformat(text)
    return int((dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp() * 1000)


def _iso(ms: int | None) -> str:
    return "—" if ms is None else datetime.fromtimestamp(ms / 1000, tz=UTC).strftime(
        "%Y-%m-%d %H:%M")


def _now() -> int:
    return int(time.time() * 1000)


def _why(q: dict | None) -> str:
    if q is None:
        return "sin puntuar"
    if q["state"] != "descartado":
        return q["state"]
    return "descartado: " + "; ".join(REASONS.get(r, r) for r in q["reasons"])


def _dims(q: dict | None) -> str:
    if not q:
        return ""
    b = q["breakdown"]
    return (f"tema {b['tema']['value']:.2f} · actualidad {b['actualidad']['value']:.2f} · "
            f"prioridad {b['prioridad']['value']:.2f} → {q['score']:.2f} (umbral "
            f"{b['threshold']:.2f})")


def cmd_discover(cat: VideoCatalog, wl: W.Watchlist, a) -> int:
    now = _now()
    api, rss = sources(cat, wl, now)
    since = _ms(a.since) if getattr(a, "since", None) else None
    kind = "backfill" if a.cmd == "backfill" else "discover"
    res = run_discover(cat, wl, now, api, rss, channels=a.channel or None, since_ms=since,
                       kind=kind, mode="historico" if kind == "backfill" else "vivo")
    for c in res["channels"]:
        state = "ok" if c["ok"] else f"ERROR {c['error']}"
        print(f"{c['channel_id']}  {state}  videos={c['videos']} nuevos={c.get('added', 0)} "
              f"cambiados={c.get('changed', 0)} unidades={c['units']}")
    q = res["queue"]
    print(f"borrados={res['deleted']} · cola: +{q['pendiente']} pendientes, "
          f"{q['descartado']} descartados · cómputo hoy {q['compute_used_s'] / 3600:.2f}/"
          f"{q['compute_cap_s'] / 3600:.2f} h · cuota {res['quota_used_today']}/"
          f"{res['quota_limit']} unidades")
    return 0 if any(c["ok"] for c in res["channels"]) else 1


def cmd_queue(cat: VideoCatalog, wl: W.Watchlist, a) -> int:
    day = utc_day(_now())
    cap = wl.budget.compute_hours_per_day
    print(f"Cómputo admitido hoy ({day}): {cat.used_compute_s(day) / 3600:.2f} de {cap:.2f} h")
    for q in cat.queue_rows(state=a.state):
        if a.state is None and q["state"] == "descartado":
            continue
        print(f"{q['video_id']}  {q['state']:<10} {q['score']:.2f}  "
              f"{(q['est_compute_s'] or 0) / 60:.1f} min  día={q['admitted_day'] or '—'}  "
              f"{q['mode']}")
    return 0


def cmd_list(cat: VideoCatalog, wl: W.Watchlist, a) -> int:
    asof = _ms(a.asof) if a.asof else _now()
    vids = cat.videos_asof(asof, a.channel)
    print(f"{len(vids)} videos conocidos a {_iso(asof)} UTC (lista {wl.version})")
    for v in vids[: a.limit]:
        q = cat.queue_get(v["video_id"])
        print(f"- {v['video_id']}  {_iso(v['published_at'])}  {v['title'][:70]}")
        print(f"    {_why(q)}")
        if q:
            print(f"    {_dims(q)}")
    return 0


def cmd_show(cat: VideoCatalog, wl: W.Watchlist, a) -> int:
    vers = cat.versions(a.video_id)
    if not vers:
        print("No está en el catálogo.")
        return 1
    print(f"Primera vez visto: {_iso(vers[0]['seen_at'])} UTC (antes no existía para el sistema)")
    for v in vers:
        tag = "BORRADO" if v["deleted"] else v["source"]
        print(f"  {_iso(v['seen_at'])}  [{tag}]  {v['title']}  ({v['duration_s']} s, "
              f"{v['language']}, {v['live']}, lista {v['wl_version']})")
    q = cat.queue_get(a.video_id)
    print(_why(q))
    if q:
        print(_dims(q))
        print(json.dumps(q["breakdown"], ensure_ascii=False, indent=2))
    return 0


def cmd_coverage(cat: VideoCatalog, wl: W.Watchlist, a) -> int:
    rows = cat.coverage()
    if not rows:
        print("Sin consultas registradas: el catálogo está vacío.")
    for r in rows:
        ch = wl.channel(r["channel_id"])
        print(f"{r['channel_id']} ({ch.name if ch else 'fuera de la lista'}): "
              f"{r['fetch_ok']} consultas ok, {r['fetch_failed']} fallidas · {r['videos']} videos "
              f"publicados {_iso(r['published_min'])} → {_iso(r['published_max'])} · última ok "
              f"{_iso(r['last_ok'])}" + (f" · último error: {r['last_error']}"
                                          if r["last_error"] else ""))
    return 0


def cmd_run(wl: W.Watchlist, a) -> int:
    from eim.data.video.service import serve
    return serve(Path(a.data_dir), wl, every_s=a.every_min * 60, once=a.once)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m eim.video", description=__doc__.splitlines()[0])
    p.add_argument("--data-dir", default="data")
    p.add_argument("--watchlist", default=W.DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--channel", action="append")
    b = sub.add_parser("backfill")
    b.add_argument("--channel", action="append", required=True)
    b.add_argument("--since", required=True)
    sub.add_parser("queue").add_argument("--state")
    li = sub.add_parser("list")
    li.add_argument("--asof")
    li.add_argument("--channel")
    li.add_argument("--limit", type=int, default=50)
    sub.add_parser("show").add_argument("video_id")
    sub.add_parser("coverage")
    r = sub.add_parser("run")
    r.add_argument("--every-min", type=float, default=60)
    r.add_argument("--once", action="store_true")
    a = p.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    wl = W.load(a.watchlist)
    if a.cmd == "run":   # el servicio abre el catálogo solo durante cada pasada
        return cmd_run(wl, a)
    cat = VideoCatalog(catalog_path(a.data_dir))
    try:
        return {"discover": cmd_discover, "backfill": cmd_discover, "queue": cmd_queue,
                "list": cmd_list, "show": cmd_show, "coverage": cmd_coverage}[a.cmd](cat, wl, a)
    finally:
        cat.close()


if __name__ == "__main__":
    sys.exit(main())
