"""Lectura de las liquidaciones en vivo y agregados por vela (sin red)."""

from __future__ import annotations

from pathlib import Path

import duckdb

from eim.core import LiqBar


def _glob(root: Path, kind: str, symbol: str) -> str | None:
    base = root / "micro" / kind / f"symbol={symbol}"
    if not any(base.glob("date=*/hour=*/part-*.parquet")):
        return None
    return (base / "date=*" / "hour=*" / "part-*.parquet").as_posix().replace("'", "''")


def _read(root: Path, kind: str, symbol: str, cols: str, where: str, start: int, end: int):
    g = _glob(root, kind, symbol)
    if g is None:
        return []
    q = (f"SELECT {cols} FROM read_parquet('{g}', hive_partitioning=false) "
         f"WHERE t >= ? AND t < ? AND {where} ORDER BY t")
    return duckdb.connect().execute(q, [start, end]).fetchall()


def aggregate(rows: list[tuple], gaps: list[int], t0: int, step: int, n: int) -> list[LiqBar]:
    """Agrega por vela `[t0 + i·step, +step)`; solo devuelve velas con la recolección VIVA.

    rows: (t, venue, long_pos, usd); las filas `alive:<bolsa>` (usd 0) prueban que el recolector
    estaba conectado: una vela con marca de vida y sin liquidaciones es un cero REAL, mientras que
    una vela sin ninguna marca no se devuelve (sin datos, nunca ceros inventados).
    """
    longs, shorts, cnt = [0.0] * n, [0.0] * n, [0] * n
    venue: list[dict[str, float]] = [{} for _ in range(n)]
    seen = [False] * n
    for t, v, long_pos, usd in rows:
        i = (t - t0) // step
        if not 0 <= i < n:
            continue
        seen[i] = True
        if v.startswith("alive:"):
            continue
        cnt[i] += 1
        (longs if long_pos else shorts)[i] += usd
        venue[i][v] = venue[i].get(v, 0.0) + usd
    bad = {(g - t0) // step for g in gaps}
    return [LiqBar(t=t0 + i * step, long_usd=longs[i], short_usd=shorts[i], count=cnt[i],
                   by_venue=venue[i], complete=i not in bad)
            for i in range(n) if seen[i]]


def read_liq_flow(root: str | Path, symbol: str, t0: int, step: int, n: int) -> list[LiqBar]:
    root, end = Path(root), t0 + n * step
    rows = _read(root, "liqs", symbol, "t, venue, long_pos, usd", "true", t0, end)
    gaps = [r[0] for r in _read(root, "gaps", symbol, "t", "stream LIKE 'liq:%'", t0, end)]
    return aggregate(rows, gaps, t0, step, n)
