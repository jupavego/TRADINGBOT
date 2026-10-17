"""Carga `ArbHistory` (entrada pura del simulador T43) desde el almacén y las capturas.

Lo que falta queda en `missing` con su motivo. Profundidad: capturas reales guardadas por
`arb_history_sync` (`root/arb_history/arbitrage/`) y por el escáner en vivo
(`root/arbitrage/`); el volumen de referencia de cada perfil es el de las 24 velas previas
a su captura (para adelgazar el libro en épocas de menos volumen).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from eim.arbitrage.sim.depth import DepthProfile
from eim.arbitrage.sim.frame import ArbHistory, AssetHistory, Bars, Quarterly
from eim.arbitrage.sim.replay import quarter_key, spot_key
from eim.core import ArbMarket, Book, SpotPair
from eim.data.arb_history_sync import (
    H_MS,
    HIST_DIR,
    START,
    quarterly_deliveries,
    quarterly_symbol,
)
from eim.data.arb_store import ArbStore
from eim.data.store import Store

SPOT = "spot_candles"


def _bars(store: Store, symbol: str, tf: str, kind: str, start: int | None,
          end: int | None) -> Bars | None:
    rows = store.read_candles(symbol, tf, start, end, kind=kind)
    if not rows:
        return None
    return Bars.from_candles(rows, store.source(kind, symbol, tf) or "desconocida")


def _cut(b: Bars, t1: int) -> Bars:
    k = int(np.searchsorted(b.t, t1))
    return Bars(t=b.t[:k], o=b.o[:k], h=b.h[:k], l=b.l[:k], c=b.c[:k], vq=b.vq[:k],
                source=b.source)


def _quarterly(store: Store, asset: str, d: int, now: int,
               missing: dict[str, str]) -> Quarterly | None:
    sym = quarterly_symbol(asset, d)
    full = _bars(store, sym, "1h", "candles", None, None)
    if full is None:
        missing[f"candles:{sym}"] = "sin velas (no listado o sin descargar)"
        return None
    settle, src = None, ""
    after = [i for i in range(len(full)) if d <= full.t[i] <= d + 3 * H_MS]
    flat = [i for i in after if full.h[i] == full.l[i] and full.vq[i] == 0]
    if flat:  # tras liquidar, el último precio queda fijo en el de liquidación
        settle, src = float(full.c[flat[0]]), f"{full.source}: vela plana tras el vencimiento"
    elif after:
        settle = float(full.c[after[-1]])
        src = f"{full.source}: último precio tras el vencimiento (aprox., sin vela plana)"
        missing[f"settle:{sym}"] = "liquidación aproximada con el último precio"
    elif d <= now:
        missing[f"settle:{sym}"] = "sin velas tras el vencimiento: sin precio de liquidación"
    return Quarterly(symbol=sym, delivery_t=d, bars=_cut(full, d), settle=settle,
                     settle_source=src)


def load_history(store: Store, root: Path, *, assets: tuple[str, ...] = ("BTC", "ETH"),
                 start: int | None = None, end: int | None = None,
                 tri: bool = True) -> ArbHistory:
    root = Path(root)
    missing: dict[str, str] = {}
    sources: dict[str, str] = {}
    coverage: dict[str, tuple[int, int]] = {}
    out: dict[str, AssetHistory] = {}
    now = end if end is not None else int(time.time() * 1000)

    def note(key: str, b: Bars | None) -> Bars | None:
        if b is None:
            missing[key] = "sin datos en el almacén"
        else:
            sources[key] = b.source
            if b.coverage:
                coverage[key] = b.coverage
        return b

    for a in assets:
        perp15 = _bars(store, f"{a}USDT", "15m", "candles", start, end)
        rets = np.diff(np.log(perp15.c)) if perp15 is not None and len(perp15) > 1 else None
        fund = store.read_series("funding", f"{a}USDT", "-", start, end)
        ufund = store.read_series("funding", f"{a}USDC", "-", start, end)
        for key, rows in ((f"funding:{a}USDT", fund), (f"funding:{a}USDC", ufund)):
            if rows:
                sources[key] = store.source("funding", key.split(":")[1]) or "desconocida"
                coverage[key] = (rows[0][0], rows[-1][0])
            else:
                missing[key] = "sin funding en el almacén"
        qs = [q for d in quarterly_deliveries(start or START, now)
              if (q := _quarterly(store, a, d, now, missing)) is not None and len(q.bars)]
        for q in qs:
            sources[f"candles:{q.symbol}"] = q.bars.source
            if q.bars.coverage:
                coverage[f"candles:{q.symbol}"] = q.bars.coverage
        out[a] = AssetHistory(
            asset=a,
            spot=note(f"spot:{a}USDT", _bars(store, f"{a}USDT", "1h", SPOT, start, end)),
            perp=note(f"candles:{a}USDT", _bars(store, f"{a}USDT", "1h", "candles", start, end)),
            funding=tuple(fund), quarterlies=tuple(qs),
            usdc_perp=note(f"candles:{a}USDC", _bars(store, f"{a}USDC", "1h", "candles", start,
                                                      end)),
            usdc_funding=tuple(ufund), returns_15m=rets)
    usdc = note("spot:USDCUSDT", _bars(store, "USDCUSDT", "1h", SPOT, start, end))
    hdir = root / HIST_DIR
    pairs: tuple[SpotPair, ...] = ()
    tri_bars: dict[str, Bars] = {}
    pf = hdir / "tri_pairs.json"
    if tri and pf.exists():
        pairs = tuple(SpotPair(**p) for p in json.loads(pf.read_text(encoding="utf-8")))
        for pr in pairs:
            b = note(f"spot:{pr.symbol}:1m", _bars(store, pr.symbol, "1m", SPOT, None, end))
            if b is not None:
                tri_bars[pr.symbol] = b
    elif tri:
        missing["tri_pairs"] = "sin pares del triangular (correr la descarga)"
    ff = hdir / "filters.json"
    filters = json.loads(ff.read_text(encoding="utf-8"))["filters"] if ff.exists() else {}
    if not filters:
        missing["filters"] = "sin mínimos de orden (exchangeInfo)"
    caps = _captures(root)
    if not caps:
        missing["depth"] = "sin capturas de libros: el deslizamiento no se puede estimar"
    profiles, refs = _profiles(caps, out, usdc)
    return ArbHistory(assets=out, usdcusdt=usdc, depth=tuple(profiles), depth_ref_vq=refs,
                      tri_bars=tri_bars, tri_pairs=pairs, captures=tuple(caps), filters=filters,
                      sources=sources, coverage=coverage, missing=missing)


def _captures(root: Path) -> list[ArbMarket]:
    caps: list[ArbMarket] = []
    for st in (ArbStore(root / HIST_DIR, keep=10**6), ArbStore(root, keep=10**6)):
        caps += st.all()
    return caps


def _profiles(caps: list[ArbMarket], assets: dict[str, AssetHistory],
              usdc: Bars | None) -> tuple[list[DepthProfile], dict[str, float]]:
    """Perfiles por clave y volumen/h medio de las 24 velas previas a cada captura."""
    profiles: list[DepthProfile] = []
    vols: dict[str, list[float]] = {}

    def add(key: str, book: Book, t: int, bars: Bars | None, usd: float = 1.0) -> None:
        prof = DepthProfile.from_book(key, book, t, usd)
        if prof is None:
            return
        profiles.append(prof)
        if bars is not None:
            k = int(np.searchsorted(bars.t, t - H_MS))
            if k > 0:
                vols.setdefault(key, []).append(float(bars.vq[max(0, k - 24):k].mean()))

    for m in caps:
        quote = {pr.symbol: pr.quote for pr in m.spot_pairs}
        for sym, book in m.spot_books.items():
            q = quote.get(sym, "USDT")
            usd = 1.0 if q == "USDT" else _mid(m.spot_books.get(f"{q}USDT"))
            if usd is None:  # sin precio de la cotizada en la captura: no se puede pasar a USD
                continue
            h = assets.get(sym.removesuffix("USDT")) if q == "USDT" else None
            bars = usdc if sym == "USDCUSDT" else (h.spot if h is not None else None)
            add(spot_key(sym), book, m.asof, bars, usd)
        for c in m.contracts:
            book = m.futures_books.get(c.symbol)
            h = assets.get(c.base)
            if book is None:
                continue
            if c.kind == "perpetual":
                bars = None if h is None else (h.perp if c.margin == "USDT" else h.usdc_perp)
                add(f"{c.market}:{c.symbol}", book, m.asof, bars)
                continue
            live = sorted(x.delivery_t or 0 for x in m.contracts
                          if x.base == c.base and x.kind == "quarterly" and x.margin == c.margin)
            rank = live.index(c.delivery_t or 0) + 1
            qbars = next((q.bars for q in h.quarterlies if q.symbol == c.symbol), None) if h \
                else None
            add(quarter_key(c.base, rank), book, m.asof, qbars)
    refs = {k: float(np.mean(v)) for k, v in vols.items() if v}
    return profiles, refs


def _mid(book: Book | None) -> float | None:
    if book is None or not book.bids or not book.asks:
        return None
    return (book.bids[0][0] + book.asks[0][0]) / 2
