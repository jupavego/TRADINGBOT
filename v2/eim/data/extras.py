"""Liquidaciones y titulares en el almacén, para el snapshot en vivo (sin red al leer).

`read_*` solo lee disco (lo usa `build_snapshot`); `sync_*` es la única con red y la llama el ciclo.
Point-in-time: a `asof` solo se ve lo publicado/visto hasta entonces.
- Liquidaciones: caché de CSV diarios en `root/liquidations/<SIMBOLO_COIN-M>/` (misma que la API).
- Titulares: `root/news/headlines.jsonl`, de solo añadir, con `seen_at` por fila.
Un dataset ausente devuelve None (el agente dice `no_data`); nunca se rellena con ceros.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from eim.core import Liquidations, NewsItem
from eim.data.providers.liquidations import (
    SOURCE,
    STALE_THRESHOLD_DAYS,
    BinanceLiquidations,
    LiquidationsUnavailable,
    aggregate,
    dedupe_rows,
    resolve_liquidation_symbol,
)
from eim.data.providers.news import fetch_headlines

_DAY_MS = 86_400_000
LIQ_DAYS = 30
NEWS_KEEP_MS = 3 * _DAY_MS


def liq_dir(root: Path) -> Path:
    return root / "liquidations"


def read_liquidations(
    root: Path, symbol: str, asof: int, days: int = LIQ_DAYS
) -> Liquidations | None:
    """Últimos `days` archivos cacheados con fecha ≤ `asof`; None si no hay ninguno."""
    try:
        liq_symbol = resolve_liquidation_symbol(symbol)
    except ValueError:
        return None
    d = liq_dir(root) / liq_symbol
    cap = datetime.fromtimestamp(asof / 1000, UTC).strftime("%Y-%m-%d")
    files = sorted(f for f in d.glob(f"{liq_symbol}-liquidationSnapshot-*.csv")
                   if f.stem.rsplit("-liquidationSnapshot-", 1)[-1] <= cap)[-days:]
    if not files:
        return None
    rows: list[dict] = []
    for f in files:
        rows += BinanceLiquidations._read_csv(f.read_text(encoding="utf-8"))
    daily, levels = aggregate(dedupe_rows(rows))
    if not daily:
        return None
    last = files[-1].stem.rsplit("-liquidationSnapshot-", 1)[-1]
    latest = datetime.strptime(last, "%Y-%m-%d").replace(tzinfo=UTC)
    age = (asof - int(latest.timestamp() * 1000)) // _DAY_MS
    return Liquidations(
        requested_symbol=symbol.upper(), liquidation_symbol=liq_symbol, most_recent_date=last,
        stale=age > STALE_THRESHOLD_DAYS, stale_age_days=int(age), days_with_data=len(files),
        daily=daily, levels=levels,
        source=f"{SOURCE}: {liq_symbol} (coin-margined) como proxy de {symbol.upper()}",
    )


def sync_liquidations(root: Path, symbol: str, *, fetcher=None) -> int:
    """Descarga a la caché los últimos días publicados. Devuelve los días con datos; 0 si el
    dataset ya no existe (Binance dejó de publicarlo en oct-2024: sigue valiendo lo cacheado)."""
    fetch = fetcher or BinanceLiquidations(cache_dir=liq_dir(root)).fetch
    try:
        return fetch(symbol, days=LIQ_DAYS).days_with_data
    except LiquidationsUnavailable:
        return 0


def _news_file(root: Path) -> Path:
    return root / "news" / "headlines.jsonl"


def read_headlines(root: Path, asof: int) -> list[NewsItem] | None:
    """Titulares vistos a `asof` (seen_at ≤ asof, t ≤ asof), más recientes primero."""
    f = _news_file(root)
    if not f.exists():
        return None
    seen: dict[str, NewsItem] = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if r["seen_at"] <= asof and r["t"] <= asof:
                seen[r["id"]] = NewsItem(**{k: r[k] for k in ("id", "t", "title", "source", "url")})
        except (ValueError, KeyError, TypeError):
            continue
    return sorted(seen.values(), key=lambda n: -n.t) or None


def sync_headlines(root: Path, now: int, *, fetcher=fetch_headlines) -> int:
    """Añade los titulares nuevos de los feeds RSS; devuelve cuántos añadió."""
    f = _news_file(root)
    known: set[str] = set()
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                known.add(json.loads(line)["id"])
            except (ValueError, KeyError):
                continue
    new = [n for n in fetcher() if n.id not in known and n.t >= now - NEWS_KEEP_MS]
    if new:
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            for n in new:
                fh.write(json.dumps({**n.model_dump(), "seen_at": now}, ensure_ascii=False) + "\n")
    return len(new)
