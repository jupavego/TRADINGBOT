"""Agregación de velas del almacén (`src` → `dst`), p. ej. 1 m → 5 m (velas de NFI, T58+).

Solo grupos completos, con DuckDB sobre el parquet; nunca pide nada a la API. `aggregate_new`
es la versión incremental que mantiene el marco al día: relee un margen de `HEAL_MS` antes de
la última vela agregada para sanar huecos del 1 m rellenados tarde.
"""

from __future__ import annotations

from eim.core import Candle
from eim.data.store import Store, _lit
from eim.data.timeframes import tf_ms

HEAL_MS = 86_400_000


def aggregate(store: Store, symbol: str, src: str = "1m", dst: str = "5m",
              since: int | None = None) -> int:
    """Agrega `src`→`dst` (desde `since`, ms, o toda la historia) y guarda. Devuelve las velas de
    `dst` escritas. El marco `dst` es solo de almacén."""
    import duckdb

    f, k = store._file("candles", symbol, src), tf_ms(dst)   # noqa: SLF001
    if not f.exists():
        return 0
    need = k // tf_ms(src)
    where = "" if since is None else f"WHERE t >= {int(since) // k * k} "
    rows = duckdb.connect().execute(
        "SELECT t // ? * ? AS g, arg_min(o, t), max(h), min(l), arg_max(c, t), sum(v), "
        f"sum(taker_buy_v), sum(trades) FROM read_parquet({_lit(f)}, hive_partitioning=false) "
        f"{where}GROUP BY 1 HAVING count(*) = ? ORDER BY 1", [k, k, need]).fetchall()
    if not rows:
        return 0
    store.upsert_candles(symbol, dst, [
        Candle(t=int(g), o=o, h=h, l=lo, c=c, v=v, taker_buy_v=tb,
               trades=None if n is None else int(n)) for g, o, h, lo, c, v, tb, n in rows],
        f"agregado de {src}")
    return len(rows)


def aggregate_new(store: Store, symbol: str, src: str = "1m", dst: str = "5m") -> int:
    """Solo lo nuevo: desde `HEAL_MS` antes de la última vela de `dst` (o todo si no hay)."""
    b = store.bounds(symbol, dst)
    return aggregate(store, symbol, src, dst, None if b is None else b[1] - HEAL_MS)
