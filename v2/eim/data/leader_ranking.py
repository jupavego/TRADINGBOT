"""Descarga del ranking público de Hyperliquid con caché en disco (todo el I/O de esta fuente)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from eim.core.leaders import Leader
from eim.data.leader_store import LeaderStore
from eim.leaders import params as P
from eim.leaders.ranking import pick


class RankingUnavailable(RuntimeError):
    """La fuente no respondió o cambió de formato: se avisa, no se inventa nada."""


def load_rows(root: str | Path, *, client: httpx.Client | None = None,
              clock=lambda: int(time.time() * 1000), url: str = P.RANKING_URL) -> list[dict]:
    """Filas del ranking; usa la copia en disco si tiene menos de `RANKING_CACHE_S`."""
    cache = Path(root) / "leaders" / "ranking_cache.json"
    if cache.exists() and clock() - int(cache.stat().st_mtime * 1000) < P.RANKING_CACHE_S * 1000:
        return json.loads(cache.read_text(encoding="utf-8"))
    http = client or httpx.Client(timeout=120.0, follow_redirects=True)
    try:
        r = http.get(url)
        r.raise_for_status()
        if len(r.content) > P.RANKING_MAX_BYTES:
            raise RankingUnavailable(f"respuesta anómala ({len(r.content)} bytes)")
        rows = r.json()["leaderboardRows"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("sin filas")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise RankingUnavailable(f"ranking no disponible o con otro formato: {exc}") from exc
    finally:
        if client is None:
            http.close()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def discover_ranking(store: LeaderStore, root: str | Path, top: int = P.DISCOVERY_TOP, *,
                     clock=lambda: int(time.time() * 1000), client=None) -> list[Leader]:
    """Registra como candidatos los mejores del ranking que pasan el filtro previo."""
    now = clock()
    found = pick(load_rows(root, client=client, clock=clock), now, top=top)
    return [ld for ld in found if store.upsert_leader(ld, now)]
