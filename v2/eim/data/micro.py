"""Lectura de la recolección de microestructura y agregados por vela (sin red)."""

from __future__ import annotations

import json
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


def aggregate(
    trades: list[tuple], tops: list[tuple], gaps: list[int], t0: int, step: int, n: int
) -> list[MicroBar]:
    """Agrega por vela `[t0 + i·step, +step)`. Solo devuelve velas con datos.

    trades: (t, p, q, maker) · tops: (t, bid_p, bid_q, ask_p, ask_q, bids_json, asks_json) ·
    gaps: instantes (ms) de huecos de secuencia. Los pares de muestras que cruzan un hueco
    no aportan OFI (el libro se reconstruyó entre ambas).
    """
    idx = lambda t: (t - t0) // step  # noqa: E731
    buy = [0.0] * n
    sell = [0.0] * n
    cnt = [0] * n
    for t, _p, q, maker in trades:
        i = idx(t)
        if 0 <= i < n:
            cnt[i] += 1
            if maker:  # el comprador es maker → el agresor vende
                sell[i] += q
            else:
                buy[i] += q
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
            bq = sum(q for _, q in json.loads(row[5]))
            aq = sum(q for _, q in json.loads(row[6]))
            if bq + aq > 0:
                imb_sum[i] += (bq - aq) / (bq + aq)
                imb_n[i] += 1
            if prev is not None and not any(prev[0] < g <= t for g in gaps_sorted):
                ofi[i] += _ofi_step(prev[1], cur)
        prev = (t, cur)
    return [
        MicroBar(t=t0 + i * step, ofi=ofi[i], delta=buy[i] - sell[i], buy_v=buy[i],
                 sell_v=sell[i], trades=cnt[i],
                 depth_imb=imb_sum[i] / imb_n[i] if imb_n[i] else None, complete=not bad[i])
        for i in range(n) if cnt[i] or seen[i]
    ]


def read_micro(
    root: str | Path, symbol: str, t0: int, step: int, n: int
) -> tuple[list[MicroBar], Book | None]:
    """Agregados por vela de las `n` velas desde `t0` y el último libro top-10 de la ventana."""
    root = Path(root)
    end = t0 + n * step
    trades = _read(root, "trades", symbol, "t, p, q, maker", t0, end)
    tops = _read(root, "top", symbol, "t, bid_p, bid_q, ask_p, ask_q, bids, asks", t0, end)
    # una muestra previa a la ventana evita perder el OFI del primer par
    gaps = [r[0] for r in _read(root, "gaps", symbol, "t", t0, end)]
    bars = aggregate(trades, tops, gaps, t0, step, n)
    book = None
    if tops:
        last = tops[-1]
        book = Book(bids=[tuple(x) for x in json.loads(last[5])],
                    asks=[tuple(x) for x in json.loads(last[6])],
                    source="binance_ws:top10")
    return bars, book
