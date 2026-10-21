"""Lectura de la recolección de microestructura y agregados por vela (sin red)."""

from __future__ import annotations

import json
from bisect import bisect_right
from pathlib import Path

import duckdb

from eim.core import Book, MicroBar


def _glob(root: Path, kind: str, symbol: str) -> str | None:
    base = root / "micro" / kind / f"symbol={symbol}"
    if not any(base.glob("date=*/hour=*/part-*.parquet")):
        return None
    return (base / "date=*" / "hour=*" / "part-*.parquet").as_posix().replace("'", "''")


def _read(root: Path, kind: str, symbol: str, cols: str, start: int, end: int) -> list[tuple]:
    g = _glob(root, kind, symbol)
    if g is None:
        return []
    q = (f"SELECT {cols} FROM read_parquet('{g}', hive_partitioning=false) "
         f"WHERE t >= ? AND t < ? ORDER BY t")
    return duckdb.connect().execute(q, [start, end]).fetchall()


def _ofi_step(prev: tuple, cur: tuple) -> float:
    """Evento OFI entre dos muestras (bid_p, bid_q, ask_p, ask_q) del mejor nivel."""
    bp0, bq0, ap0, aq0 = prev
    bp1, bq1, ap1, aq1 = cur
    e = (bq1 if bp1 >= bp0 else 0.0) - (bq0 if bp1 <= bp0 else 0.0)
    e -= (aq1 if ap1 <= ap0 else 0.0) - (aq0 if ap1 >= ap0 else 0.0)
    return e


def _trade_bars(trades: list[tuple], t0: int, step: int, n: int) -> dict[int, tuple]:
    """Reduce trades (t, p, q, maker) a {vela: (compra, venta, nº)} (versión en memoria)."""
    out: dict[int, list] = {}
    for t, _p, q, maker in trades:
        i = (t - t0) // step
        if 0 <= i < n:
            b = out.setdefault(i, [0.0, 0.0, 0])
            b[1 if maker else 0] += q   # el comprador es maker → el agresor vende
            b[2] += 1
    return {i: tuple(v) for i, v in out.items()}


def aggregate(
    trades: list[tuple], tops: list[tuple], gaps: list[int], t0: int, step: int, n: int
) -> list[MicroBar]:
    """Agrega por vela `[t0 + i·step, +step)`. Solo devuelve velas con datos.

    trades: (t, p, q, maker) · tops: (t, bid_p, bid_q, ask_p, ask_q, bids_json, asks_json) ·
    gaps: instantes (ms) de huecos de secuencia. Los pares de muestras que cruzan un hueco
    no aportan OFI (el libro se reconstruyó entre ambas).
    """
    sums = [(r[0], r[1], r[2], r[3], r[4], sum(q for _, q in json.loads(r[5])),
             sum(q for _, q in json.loads(r[6]))) for r in tops]
    return combine(_trade_bars(trades, t0, step, n), sums, gaps, t0, step, n)


def combine(
    tb: dict[int, tuple], tops: list[tuple], gaps: list[int], t0: int, step: int, n: int
) -> list[MicroBar]:
    """Como `aggregate`, con los trades ya reducidos por vela (`tb`: i → (compra, venta, nº)) y
    cada top como (t, bid_p, bid_q, ask_p, ask_q, suma_qty_bids, suma_qty_asks)."""
    idx = lambda t: (t - t0) // step  # noqa: E731
    buy = [tb.get(i, (0.0, 0.0, 0))[0] for i in range(n)]
    sell = [tb.get(i, (0.0, 0.0, 0))[1] for i in range(n)]
    cnt = [tb.get(i, (0.0, 0.0, 0))[2] for i in range(n)]
    ofi = [0.0] * n
    imb_sum = [0.0] * n
    imb_n = [0] * n
    seen = [False] * n
    bad = [False] * n
    for g in gaps:
        if 0 <= idx(g) < n:
            bad[idx(g)] = True
    gaps_sorted = sorted(gaps)
    prev = None
    for row in tops:
        t = row[0]
        i = idx(t)
        cur = row[1:5]
        if 0 <= i < n:
            seen[i] = True
            bq, aq = row[5], row[6]
            if bq + aq > 0:
                imb_sum[i] += (bq - aq) / (bq + aq)
                imb_n[i] += 1
            if prev is not None and (bisect_right(gaps_sorted, t)
                                     == bisect_right(gaps_sorted, prev[0])):  # sin hueco
                ofi[i] += _ofi_step(prev[1], cur)
        prev = (t, cur)
    return [
        MicroBar(t=t0 + i * step, ofi=ofi[i], delta=buy[i] - sell[i], buy_v=buy[i],
                 sell_v=sell[i], trades=cnt[i],
                 depth_imb=imb_sum[i] / imb_n[i] if imb_n[i] else None, complete=not bad[i])
        for i in range(n) if cnt[i] or seen[i]
    ]


def _read_trade_bars(root: Path, symbol: str, t0: int, step: int, n: int) -> dict[int, tuple]:
    """Trades reducidos por vela dentro de DuckDB (no se traen millones de filas a Python)."""
    g = _glob(root, "trades", symbol)
    if g is None:
        return {}
    q = (f"SELECT CAST(floor((t - ?) / ?) AS BIGINT) i, "
         f"SUM(CASE WHEN maker THEN 0 ELSE q END), SUM(CASE WHEN maker THEN q ELSE 0 END), "
         f"COUNT(*) FROM read_parquet('{g}', hive_partitioning=false) "
         f"WHERE t >= ? AND t < ? GROUP BY 1")
    rows = duckdb.connect().execute(q, [t0, step, t0, t0 + n * step]).fetchall()
    return {int(i): (float(b), float(s), int(c)) for i, b, s, c in rows if 0 <= i < n}


def _read_tops(root: Path, symbol: str, start: int, end: int) -> list[tuple]:
    """(t, bid_p, bid_q, ask_p, ask_q, Σ qty bids, Σ qty asks): la suma de niveles se hace en
    DuckDB para no analizar el JSON de cada libro en Python."""
    g = _glob(root, "top", symbol)
    if g is None:
        return []
    q = ("SELECT t, bid_p, bid_q, ask_p, ask_q, "
         "list_sum(CAST(json_extract(bids, '$[*][1]') AS DOUBLE[])), "
         "list_sum(CAST(json_extract(asks, '$[*][1]') AS DOUBLE[])) "
         f"FROM read_parquet('{g}', hive_partitioning=false) WHERE t >= ? AND t < ? ORDER BY t")
    return [(r[0], r[1], r[2], r[3], r[4], r[5] or 0.0, r[6] or 0.0)
            for r in duckdb.connect().execute(q, [start, end]).fetchall()]


def _last_top_levels(root: Path, symbol: str, start: int, end: int):
    g = _glob(root, "top", symbol)
    if g is None:
        return None
    q = (f"SELECT bids, asks FROM read_parquet('{g}', hive_partitioning=false) "
         f"WHERE t >= ? AND t < ? ORDER BY t DESC LIMIT 1")
    row = duckdb.connect().execute(q, [start, end]).fetchone()
    return row


def read_micro(
    root: str | Path, symbol: str, t0: int, step: int, n: int
) -> tuple[list[MicroBar], Book | None]:
    """Agregados por vela de las `n` velas desde `t0` y el último libro top-10 de la ventana."""
    root = Path(root)
    end = t0 + n * step
    tb = _read_trade_bars(root, symbol, t0, step, n)
    tops = _read_tops(root, symbol, t0, end)
    gaps = [r[0] for r in _read(root, "gaps", symbol, "t", t0, end)]
    bars = combine(tb, tops, gaps, t0, step, n)
    book = None
    last = _last_top_levels(root, symbol, t0, end) if tops else None
    if last:
        book = Book(bids=[tuple(x) for x in json.loads(last[0])],
                    asks=[tuple(x) for x in json.loads(last[1])],
                    source="binance_ws:top10")
    return bars, book
