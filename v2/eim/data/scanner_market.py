"""E/S del escáner global (T93): catálogo, panel del universo, ventanas, cotizaciones y relleno.

El escáner (`eim/scanner/`) es puro donde puede; todo lo que toca disco o red pasa por aquí.

- **Catálogo** (`read_catalog`, `refresh_catalog`): el registro de T89 en `instruments.duckdb`.
  Se abre, se lee y se cierra: ningún servicio lo deja abierto. `refresh_catalog` es el
  descubrimiento de T89 (UNA llamada pública a `exchangeInfo`, peso 1) con las bajas del ámbito
  `venue=binance`: así quedan fechadas las altas, bajas y vencimientos.
- **Panel** (`load_panel`): las últimas `width` velas cerradas de cientos de símbolos en UNA
  consulta DuckDB sobre el almacén del universo (`data/universe_perps/`, el formato de `Store`
  que dejó T181), sin crear un objeto por vela. Entre los dos tramos de una serie gana el vivo,
  igual que en `Store.sql_source`.
- **Relleno** (`sync_symbol`): las velas que faltan de un perpetuo, como mucho `days` días atrás.
  La espera entre llamadas la pone la cola (`RateLimiter`), no el proveedor.
- **Cotizaciones** (`book_tickers`): mejor compra/venta de todos los perpetuos en UNA llamada
  (`/fapi/v1/ticker/bookTicker`, peso 5).
"""

from __future__ import annotations

import time
from pathlib import Path

import duckdb
import numpy as np

from eim.core import Candle
from eim.data.duck import tune
from eim.data.store import Store
from eim.scanner.panel import Panel, empty_panel, from_rows

UNIVERSE_DIR = "universe_perps"          # el almacén de T181 (`eim/data/perp_universe.py`)
SOURCE = "binance-futures (escáner global, T93)"
DAY_MS = 86_400_000


def universe_root(data_dir: str | Path) -> Path:
    return Path(data_dir) / UNIVERSE_DIR


def _lit(path: Path | str) -> str:
    return "'" + Path(path).as_posix().replace("'", "''") + "'"


# --- catálogo ---------------------------------------------------------------------------------
def read_catalog(data_dir: str | Path, venue: str | None = None, *, events_since: int = 0):
    """(fichas, eventos desde `events_since`) del catálogo; ([], []) si aún no existe."""
    from eim.data.instruments_store import DB_NAME, open_store

    if not (Path(data_dir) / DB_NAME).exists():
        return [], []
    store = open_store(data_dir)
    try:
        insts = store.list(venue=venue)
        evs = [e for e in store.events() if e.t >= events_since]
    finally:
        store.close()
    return insts, evs


def refresh_catalog(data_dir: str | Path, futures=None) -> dict:
    """Descubrimiento de T89 sobre los USDⓈ-M de Binance (1 llamada) con bajas fechadas."""
    from eim.data.instruments_store import open_store
    from eim.data.providers.binance import BinanceFutures
    from eim.instruments import discovery, registry

    futures = futures or BinanceFutures()
    found = registry.curate_all(discovery.from_binance_usdm(
        futures.request("/fapi/v1/exchangeInfo")))
    store = open_store(data_dir)
    try:
        res = store.sync(found, scope={"venue": "binance"})
        return {"found": len(found), **res.as_json(), "by_status": store.by_status()}
    finally:
        store.close()


# --- velas ------------------------------------------------------------------------------------
def has_series(root: str | Path, timeframe: str) -> bool:
    base = Path(root) / "candles"
    return base.exists() and any(base.glob(f"symbol=*/timeframe={timeframe}/*.parquet"))


def load_panel(root: str | Path, sym_ids: dict[str, str], timeframe: str, width: int,
               cut: int) -> Panel:
    """Últimas `width` velas con `t < cut` de cada símbolo pedido (símbolo → id)."""
    if not sym_ids:
        return empty_panel(width)
    if not has_series(root, timeframe):
        e = np.zeros(0)
        return from_rows(sym_ids, np.array([], dtype=str), e.astype(np.int64), e, e, e, e, e,
                         width)
    pattern = _lit(Path(root) / "candles" / "symbol=*" / f"timeframe={timeframe}" / "*.parquet")
    q = f"""
        WITH raw AS (
            SELECT symbol, t, o, h, l, c, v, filename
            FROM read_parquet({pattern}, hive_partitioning = true, union_by_name = true,
                              filename = true,
                              hive_types = {{'symbol': VARCHAR, 'timeframe': VARCHAR}})
            WHERE t < ? AND symbol IN (SELECT unnest(?::VARCHAR[]))
        ), dedup AS (
            SELECT * FROM raw QUALIFY row_number() OVER (
                PARTITION BY symbol, t ORDER BY (filename LIKE '%data.parquet') DESC) = 1
        ), lastn AS (
            SELECT * FROM dedup QUALIFY row_number() OVER (
                PARTITION BY symbol ORDER BY t DESC) <= ?
        )
        SELECT symbol, t, o, h, l, c, v FROM lastn ORDER BY symbol, t"""
    con = duckdb.connect()
    try:
        tune(con)
        a = con.execute(q, [int(cut), sorted(sym_ids), int(width)]).fetchnumpy()
    finally:
        con.close()
    f = {k: np.asarray(a[k], dtype=np.int64 if k == "t" else float) for k in "tohlcv"}
    return from_rows(sym_ids, np.asarray(a["symbol"], dtype=str), f["t"], f["o"], f["h"],
                     f["l"], f["c"], f["v"], width)


def latest_t(root: str | Path, timeframe: str) -> int | None:
    """Apertura de la vela más reciente de todo el universo (para fijar `asof` reproducible)."""
    if not has_series(root, timeframe):
        return None
    pattern = _lit(Path(root) / "candles" / "symbol=*" / f"timeframe={timeframe}" / "*.parquet")
    con = duckdb.connect()
    try:
        tune(con)
        row = con.execute(f"SELECT max(t) FROM read_parquet({pattern}, "
                          "hive_partitioning = false, union_by_name = true)").fetchone()
    finally:
        con.close()
    return int(row[0]) if row and row[0] is not None else None


def read_window(root: str | Path, symbol: str, timeframe: str, n: int, cut: int) -> list[Candle]:
    """Últimas `n` velas con `t < cut` de un símbolo (las mismas que entraron en el panel)."""
    return Store(root).read_candles(symbol, timeframe, end=cut, last=n)


def sync_symbol(root: str | Path, symbol: str, timeframe: str, now: int, days: int,
                futures=None) -> dict:
    """Descarga lo que falta desde la última vela guardada (o `days` días atrás)."""
    from eim.data.providers.binance import BinanceFutures
    from eim.data.timeframes import tf_ms

    store = Store(root)
    step = tf_ms(timeframe)
    floor = now - days * DAY_MS
    b = store.bounds(symbol, timeframe)
    start = max(floor - floor % step, b[1] + step if b else 0)
    if start >= now - step:
        return {"symbol": symbol, "fetched": 0, "up_to_date": True}
    futures = futures or BinanceFutures(min_interval=0.0)
    cs = futures.klines(symbol, timeframe, start, now, limit=1000)   # peso 5, no 10
    closed = [c for c in cs if c.t + step <= now]
    if closed:
        store.upsert_candles(symbol, timeframe, closed, SOURCE)
    return {"symbol": symbol, "fetched": len(closed), "up_to_date": False}


# --- cotizaciones -----------------------------------------------------------------------------
def book_tickers(futures=None, now: int | None = None) -> dict[str, tuple[float, float, int]]:
    """{símbolo: (bid, ask, t)} de todos los perpetuos USDⓈ-M en una llamada."""
    from eim.data.providers.binance import BinanceFutures

    futures = futures or BinanceFutures()
    now = int(time.time() * 1000) if now is None else now
    out: dict[str, tuple[float, float, int]] = {}
    for row in futures.request("/fapi/v1/ticker/bookTicker") or []:
        try:
            bid, ask = float(row["bidPrice"]), float(row["askPrice"])
        except (KeyError, TypeError, ValueError):
            continue
        out[str(row.get("symbol"))] = (bid, ask, int(row.get("time") or now))
    return out
