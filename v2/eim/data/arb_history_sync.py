"""Descarga del histórico de arbitraje al almacén (T43). Todo es REST público sin claves.

- Futuros (`candles`): perpetuos {A}USDT y {A}USDC en 1 h (y {A}USDT en 15 min para el
  riesgo de latencia) y cada trimestral {A}USDT_AAMMDD desde su listado hasta su
  vencimiento (Binance sigue sirviendo los vencidos; la vela plana posterior trae el precio
  real de liquidación).
- Spot (`spot_candles`): {A}USDT y USDCUSDT en 1 h; pares del triangular en 1 min (últimos
  `tri_days` días: no hay profundidad histórica, se evalúa solo con ticker).
- Funding realizado de los perpetuos (`funding`).
- Mínimos de orden (`exchangeInfo`) y capturas reales de libros (`load_arb_market`) en
  `root/arb_history/`: son la única profundidad disponible.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from eim.data.arb_market import TRI_ASSETS, load_arb_market
from eim.data.arb_store import ArbStore
from eim.data.providers.binance_arb import BinanceArbData, SpotKlines
from eim.data.store import Store
from eim.data.sync import sync_candles

HIST_DIR = "arb_history"
H_MS = 3_600_000
DAY_MS = 24 * H_MS
START = 1_672_531_200_000  # 2023-01-01 UTC
LISTING_DAYS = 200  # un trimestral se lista hasta ~2 trimestres antes de vencer


def quarterly_deliveries(start: int, end: int) -> list[int]:
    """Vencimientos trimestrales de Binance (último viernes de mar/jun/sep/dic, 08:00 UTC)
    que caen en [start, end + LISTING_DAYS]."""
    out: list[int] = []
    first = datetime.fromtimestamp(start / 1000, UTC).year
    last = datetime.fromtimestamp((end + LISTING_DAYS * DAY_MS) / 1000, UTC).year
    for year in range(first, last + 1):
        for month in (3, 6, 9, 12):
            nxt = datetime(year + (month == 12), month % 12 + 1, 1, 8, tzinfo=UTC)
            day = nxt - timedelta(days=1)
            day -= timedelta(days=(day.weekday() - 4) % 7)
            t = int(day.timestamp() * 1000)
            if start <= t <= end + LISTING_DAYS * DAY_MS:
                out.append(t)
    return out


def quarterly_symbol(asset: str, delivery_t: int) -> str:
    return f"{asset}USDT_{datetime.fromtimestamp(delivery_t / 1000, UTC):%y%m%d}"


def sync_history(store: Store, prov: BinanceArbData, root: Path, *,
                 assets: tuple[str, ...] = ("BTC", "ETH"), start: int = START,
                 end: int | None = None, tri_days: int = 30, snapshots: int = 3,
                 snapshot_gap_s: float = 20.0,
                 log: Callable[[str], None] = print) -> dict[str, object]:
    """Rellena lo que falta (incremental). Devuelve un resumen con los errores por pieza."""
    end = end if end is not None else prov.clock()
    fut, spot = prov.futures, SpotKlines(prov)
    out: dict[str, object] = {}
    errors: dict[str, str] = {}

    def run(key: str, fn: Callable[[], object]) -> None:
        try:
            out[key] = fn()
            log(f"{key}: {out[key]}")
        except Exception as exc:  # noqa: BLE001 — se registra y el informe lo declara
            errors[key] = f"{type(exc).__name__}: {exc}"[:240]
            log(f"{key}: ERROR {errors[key]}")

    for a in assets:
        for sym in (f"{a}USDT", f"{a}USDC"):
            run(f"candles:{sym}:1h", lambda s=sym: sync_candles(store, fut, s, "1h", start, end))
            run(f"funding:{sym}", lambda s=sym: _sync_funding(store, prov, s, start, end))
        run(f"candles:{a}USDT:15m",
            lambda a=a: sync_candles(store, fut, f"{a}USDT", "15m", start, end))
        run(f"spot:{a}USDT:1h", lambda a=a: sync_candles(store, spot, f"{a}USDT", "1h", start,
                                                         end, kind="spot_candles"))
        for d in quarterly_deliveries(start, end):
            sym = quarterly_symbol(a, d)
            b = store.bounds(sym, "1h")
            if b is not None and b[1] >= min(d, end - 2 * H_MS):
                continue  # vencido y completo
            run(f"candles:{sym}:1h", lambda s=sym, d=d: sync_candles(
                store, fut, s, "1h", max(start, d - LISTING_DAYS * DAY_MS),
                min(end, d + 3 * H_MS)))
    run("spot:USDCUSDT:1h", lambda: sync_candles(store, spot, "USDCUSDT", "1h", start, end,
                                                 kind="spot_candles"))
    hdir = Path(root) / HIST_DIR
    hdir.mkdir(parents=True, exist_ok=True)
    tri = set(TRI_ASSETS)
    pairs = [p for p in prov.spot_pairs() if p.base in tri and p.quote in tri]
    (hdir / "tri_pairs.json").write_text(json.dumps([p.model_dump() for p in pairs]),
                                         encoding="utf-8")
    for pr in pairs:
        run(f"spot:{pr.symbol}:1m", lambda s=pr.symbol: sync_candles(
            store, spot, s, "1m", end - tri_days * DAY_MS, end, kind="spot_candles"))
    syms = {f"{a}{m}" for a in assets for m in ("USDT", "USDC")} | {"USDCUSDT"}
    syms |= {p.symbol for p in pairs}
    syms |= {c.symbol for c in prov.futures_contracts() if c.base in assets}
    run("filters", lambda: _save_filters(prov, syms, hdir, end))
    arb = ArbStore(hdir, keep=500)
    for k in range(snapshots):
        if k:
            time.sleep(snapshot_gap_s)
        run(f"depth:{k}", lambda: str(arb.save(load_arb_market(prov, assets=assets))))
    out["errors"] = errors
    return out


def _sync_funding(store: Store, prov: BinanceArbData, symbol: str, start: int,
                  end: int) -> int:
    have = store.read_series("funding", symbol)
    rows = prov.funding_history(symbol, have[-1][0] + 1 if have else start, end)
    if rows:
        store.upsert_series("funding", symbol, "-", rows, prov.futures.name)
    return len(rows)


def _save_filters(prov: BinanceArbData, syms: set[str], hdir: Path, t: int) -> int:
    filters = prov.symbol_filters(syms)
    (hdir / "filters.json").write_text(json.dumps({"t": t, "filters": filters}),
                                       encoding="utf-8")
    return len(filters)
