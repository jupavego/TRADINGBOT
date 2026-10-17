"""Almacén local: Parquet particionado por símbolo/marco, consultado con DuckDB."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from eim.core import Candle
from eim.data.timeframes import tf_ms

_CANDLE_SCHEMA = (
    "t BIGINT, o DOUBLE, h DOUBLE, l DOUBLE, c DOUBLE, v DOUBLE, taker_buy_v DOUBLE, trades BIGINT"
)
_CANDLE_COLS = "t, o, h, l, c, v, taker_buy_v, trades"


def _lit(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


class Store:
    """Parquet en `root/<kind>/symbol=S/timeframe=TF/data.parquet` + `meta.json` (fuente)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    # --- rutas ------------------------------------------------------------
    def _dir(self, kind: str, symbol: str, timeframe: str) -> Path:
        return self.root / kind / f"symbol={symbol}" / f"timeframe={timeframe}"

    def _file(self, kind: str, symbol: str, timeframe: str) -> Path:
        return self._dir(kind, symbol, timeframe) / "data.parquet"

    def source(self, kind: str, symbol: str, timeframe: str = "-") -> str | None:
        meta = self._dir(kind, symbol, timeframe) / "meta.json"
        if not meta.exists():
            return None
        return json.loads(meta.read_text(encoding="utf-8")).get("source")

    # --- velas ------------------------------------------------------------
    def upsert_candles(
        self, symbol: str, timeframe: str, candles: list[Candle], source: str,
        kind: str = "candles",
    ) -> int:
        """Inserta/reemplaza por `t`. Devuelve el total de filas tras la operación.

        `kind` separa mercados con el mismo símbolo (`candles` = futuros, `spot_candles`)."""
        tf_ms(timeframe)
        rows = [(c.t, c.o, c.h, c.l, c.c, c.v, c.taker_buy_v, c.trades) for c in candles]
        return self._upsert(kind, symbol, timeframe, rows, _CANDLE_SCHEMA, source)

    def read_candles(
        self,
        symbol: str,
        timeframe: str,
        start: int | None = None,
        end: int | None = None,
        last: int | None = None,
        kind: str = "candles",
    ) -> list[Candle]:
        """Velas con `start <= t < end`; `last=n` devuelve solo las n más recientes."""
        rows = self._read(kind, symbol, timeframe, _CANDLE_COLS, start, end, last)
        return [
            Candle(t=int(t), o=o, h=h, l=lo, c=c, v=v, taker_buy_v=tb,
                   trades=None if n is None else int(n))
            for t, o, h, lo, c, v, tb, n in rows
        ]

    def find_gaps(
        self, symbol: str, timeframe: str, start: int | None = None, end: int | None = None,
        kind: str = "candles",
    ) -> list[tuple[int, int]]:
        """Huecos como (t de la primera vela faltante, t de la última faltante)."""
        step = tf_ms(timeframe)
        ts = [c.t for c in self.read_candles(symbol, timeframe, start, end, kind=kind)]
        return [(a + step, b - step) for a, b in zip(ts, ts[1:], strict=False) if b - a > step]

    def bounds(self, symbol: str, timeframe: str,
               kind: str = "candles") -> tuple[int, int] | None:
        """(primer t, último t) almacenados, o None si no hay datos."""
        f = self._file(kind, symbol, timeframe)
        if not f.exists():
            return None
        row = duckdb.connect().execute(
            f"SELECT min(t), max(t) FROM read_parquet({_lit(f)}, hive_partitioning=false)"
        ).fetchone()
        return (int(row[0]), int(row[1])) if row and row[0] is not None else None

    # --- series (funding / open interest) ---------------------------------
    def upsert_series(
        self, kind: str, symbol: str, timeframe: str, rows: list[tuple[int, float]], source: str
    ) -> int:
        """`kind` ∈ {funding, open_interest}; el funding usa timeframe '-'."""
        return self._upsert(kind, symbol, timeframe, list(rows), "t BIGINT, x DOUBLE", source)

    def read_series(
        self,
        kind: str,
        symbol: str,
        timeframe: str = "-",
        start: int | None = None,
        end: int | None = None,
        last: int | None = None,
    ) -> list[tuple[int, float]]:
        rows = self._read(kind, symbol, timeframe, "t, x", start, end, last)
        return [(int(t), float(x)) for t, x in rows]

    # --- internos ---------------------------------------------------------
    def _upsert(
        self, kind: str, symbol: str, timeframe: str, rows: list[tuple], schema: str, source: str
    ) -> int:
        f = self._file(kind, symbol, timeframe)
        f.parent.mkdir(parents=True, exist_ok=True)
        cols = ", ".join(p.split()[0] for p in schema.split(","))
        con = duckdb.connect()
        con.execute(f"CREATE TABLE new ({schema})")
        if rows:
            ph = ", ".join("?" * len(rows[0]))
            con.executemany(f"INSERT INTO new VALUES ({ph})", rows)
        if f.exists():
            con.execute(
                f"CREATE TABLE merged AS SELECT *, 1 AS pri FROM new UNION ALL BY NAME "
                f"SELECT *, 0 AS pri FROM read_parquet({_lit(f)}, hive_partitioning=false)"
            )
        else:
            con.execute("CREATE TABLE merged AS SELECT *, 1 AS pri FROM new")
        con.execute(
            f"CREATE TABLE out AS SELECT {cols} FROM merged "
            f"QUALIFY row_number() OVER (PARTITION BY t ORDER BY pri DESC) = 1 ORDER BY t"
        )
        tmp = f.with_suffix(".tmp")
        con.execute(f"COPY out TO {_lit(tmp)} (FORMAT PARQUET)")
        tmp.replace(f)
        (f.parent / "meta.json").write_text(json.dumps({"source": source}), encoding="utf-8")
        row = con.execute("SELECT count(*) FROM out").fetchone()
        return int(row[0]) if row else 0

    def _read(
        self,
        kind: str,
        symbol: str,
        timeframe: str,
        cols: str,
        start: int | None,
        end: int | None,
        last: int | None,
    ) -> list[tuple]:
        f = self._file(kind, symbol, timeframe)
        if not f.exists():
            return []
        where: list[str] = []
        params: list[int] = []
        if start is not None:
            where.append("t >= ?")
            params.append(start)
        if end is not None:
            where.append("t < ?")
            params.append(end)
        w = f"WHERE {' AND '.join(where)}" if where else ""
        con = duckdb.connect()
        src = f"read_parquet({_lit(f)}, hive_partitioning=false)"
        if kind.endswith("candles"):  # archivos previos a T34 no tienen las opcionales
            con.execute(f"CREATE TABLE empty ({_CANDLE_SCHEMA})")
            src = f"(SELECT * FROM empty UNION ALL BY NAME SELECT * FROM {src})"
        base = f"SELECT {cols} FROM {src} {w}"
        if last is not None:
            q = f"SELECT * FROM ({base} ORDER BY t DESC LIMIT {int(last)}) ORDER BY t"
        else:
            q = f"{base} ORDER BY t"
        return con.execute(q, params).fetchall()
