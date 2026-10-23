"""Almacén local: Parquet particionado por símbolo/marco, consultado con DuckDB.

Cada serie vive en dos tramos: `data.parquet` (el vivo, el único que reescriben las escrituras
incrementales) y, si existe, `history.parquet` (el histórico, congelado: solo lo escriben
`add_history` y `compact`). Las lecturas unen los dos sin duplicar `t` (gana el vivo). Así una
serie larga y que crece cada minuto (1 min de BTCUSDT, millones de filas) no reescribe toda su
historia en cada vela nueva, y una importación de historia no compite con el escritor del tramo
vivo por el mismo archivo.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import numpy as np

from eim.core import Candle
from eim.data.timeframes import tf_ms

_CANDLE_SCHEMA = (
    "t BIGINT, o DOUBLE, h DOUBLE, l DOUBLE, c DOUBLE, v DOUBLE, taker_buy_v DOUBLE, trades BIGINT"
)
_CANDLE_COLS = "t, o, h, l, c, v, taker_buy_v, trades"
# Relación vacía con el esquema completo: los archivos previos a T34 no traen las opcionales.
_EMPTY_CANDLES = "SELECT " + ", ".join(
    f"NULL::{p.split()[1]} AS {p.split()[0]}" for p in _CANDLE_SCHEMA.split(", ")) + " WHERE false"
LIVE, HISTORY = "data.parquet", "history.parquet"
REPLACE_TRIES = 20          # reintentos si un lector tiene el archivo abierto (Windows)


def _lit(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


def _rp(path: Path) -> str:
    """Lectura de un Parquet sin columnas de partición (la ruta tiene `symbol=`/`timeframe=`)."""
    return f"read_parquet({_lit(path)}, hive_partitioning=false)"


def _replace(tmp: Path, dst: Path) -> None:
    """Sustitución atómica; en Windows falla mientras otro proceso lee `dst`: se reintenta."""
    for k in range(REPLACE_TRIES):
        try:
            tmp.replace(dst)
            return
        except PermissionError:
            if k == REPLACE_TRIES - 1:
                raise
            time.sleep(0.25)


class Store:
    """Parquet en `root/<kind>/symbol=S/timeframe=TF/{data,history}.parquet` + `meta.json`."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    # --- rutas ------------------------------------------------------------
    def _dir(self, kind: str, symbol: str, timeframe: str) -> Path:
        return self.root / kind / f"symbol={symbol}" / f"timeframe={timeframe}"

    def _file(self, kind: str, symbol: str, timeframe: str) -> Path:
        return self._dir(kind, symbol, timeframe) / LIVE

    def _parts(self, kind: str, symbol: str, timeframe: str) -> list[Path]:
        d = self._dir(kind, symbol, timeframe)
        return [p for p in (d / HISTORY, d / LIVE) if p.exists()]

    def source(self, kind: str, symbol: str, timeframe: str = "-") -> str | None:
        meta = self._dir(kind, symbol, timeframe) / "meta.json"
        if not meta.exists():
            return None
        return json.loads(meta.read_text(encoding="utf-8")).get("source")

    def sql_source(self, kind: str, symbol: str, timeframe: str, start: int | None = None,
                   end: int | None = None, dedupe: bool = True) -> str | None:
        """Subconsulta SQL con las filas de la serie en [start, end): tramo histórico + vivo, sin
        duplicar `t` (gana el vivo). None si la serie no existe."""
        parts = self._parts(kind, symbol, timeframe)
        if not parts:
            return None
        cond = [f"t >= {int(start)}"] if start is not None else []
        cond += [f"t < {int(end)}"] if end is not None else []
        w = f" WHERE {' AND '.join(cond)}" if cond else ""
        sel = [f"SELECT *, {k} AS _pri FROM {_rp(p)}{w}" for k, p in enumerate(parts)]
        if kind.endswith("candles"):
            sel.append(f"SELECT *, -1 AS _pri FROM ({_EMPTY_CANDLES})")
        union = " UNION ALL BY NAME ".join(sel)
        if dedupe and len(parts) > 1:
            union = (f"SELECT * FROM ({union}) "
                     "QUALIFY row_number() OVER (PARTITION BY t ORDER BY _pri DESC) = 1")
        return f"(SELECT * EXCLUDE (_pri) FROM ({union}))"

    # --- velas ------------------------------------------------------------
    def upsert_candles(
        self, symbol: str, timeframe: str, candles: list[Candle], source: str,
        kind: str = "candles",
    ) -> int:
        """Inserta/reemplaza por `t` en el tramo vivo. Devuelve el total de filas tras la operación.

        `kind` separa mercados con el mismo símbolo (`candles` = futuros, `spot_candles`)."""
        tf_ms(timeframe)
        return self._upsert(kind, symbol, timeframe, _rows(candles), _CANDLE_SCHEMA, source)

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

    def read_arrays(self, symbol: str, timeframe: str, start: int | None = None,
                    end: int | None = None, kind: str = "candles") -> dict[str, np.ndarray]:
        """t, o, h, l, c como arreglos (sin un objeto por vela): para millones de filas."""
        src = self.sql_source(kind, symbol, timeframe, start, end)
        if src is None:
            return {k: np.array([], dtype=np.int64 if k == "t" else float) for k in "tohlc"}
        a = duckdb.connect().execute(f"SELECT t, o, h, l, c FROM {src} ORDER BY t").fetchnumpy()
        return {k: np.asarray(a[k], dtype=np.int64 if k == "t" else float) for k in "tohlc"}

    def count(self, symbol: str, timeframe: str, kind: str = "candles") -> int:
        """Filas de la serie (sin duplicar `t` entre tramos)."""
        src = self.sql_source(kind, symbol, timeframe)
        return 0 if src is None else int(
            duckdb.connect().execute(f"SELECT count(*) FROM {src}").fetchone()[0])

    def find_gaps(
        self, symbol: str, timeframe: str, start: int | None = None, end: int | None = None,
        kind: str = "candles",
    ) -> list[tuple[int, int]]:
        """Huecos como (t de la primera vela faltante, t de la última faltante)."""
        step = tf_ms(timeframe)
        src = self.sql_source(kind, symbol, timeframe, start, end)
        if src is None:
            return []
        rows = duckdb.connect().execute(
            f"SELECT t, nxt FROM (SELECT t, lead(t) OVER (ORDER BY t) AS nxt FROM {src}) "
            f"WHERE nxt - t > {step} ORDER BY t").fetchall()
        return [(int(a) + step, int(b) - step) for a, b in rows]

    def bounds(self, symbol: str, timeframe: str,
               kind: str = "candles") -> tuple[int, int] | None:
        """(primer t, último t) almacenados, o None si no hay datos."""
        src = self.sql_source(kind, symbol, timeframe, dedupe=False)
        if src is None:
            return None
        row = duckdb.connect().execute(f"SELECT min(t), max(t) FROM {src}").fetchone()
        return (int(row[0]), int(row[1])) if row and row[0] is not None else None

    # --- tramo histórico ----------------------------------------------------
    def add_history(self, symbol: str, timeframe: str, candles: list[Candle] | Store,
                    source: str, kind: str = "candles") -> int:
        """Añade velas al tramo histórico SIN tocar el vivo: solo entran las anteriores a la
        primera vela viva (nunca tapan lo que escribe el servicio). `candles` puede ser otro
        almacén: se copia su serie con SQL, sin un objeto por vela. Devuelve las filas del
        histórico tras la operación."""
        tf_ms(timeframe)
        d = self._dir(kind, symbol, timeframe)
        d.mkdir(parents=True, exist_ok=True)
        live = d / LIVE
        con = duckdb.connect()
        cut = (con.execute(f"SELECT min(t) FROM {_rp(live)}").fetchone()[0]
               if live.exists() else None)
        if isinstance(candles, Store):
            src = candles.sql_source(kind, symbol, timeframe, end=cut) or f"({_EMPTY_CANDLES})"
            con.execute(f"CREATE TABLE new AS SELECT {_CANDLE_COLS} FROM {src}")
        else:
            con.execute(f"CREATE TABLE new ({_CANDLE_SCHEMA})")
            rows = [r for r in _rows(candles) if cut is None or r[0] < cut]
            if rows:
                con.executemany(f"INSERT INTO new VALUES ({', '.join('?' * len(rows[0]))})",
                                rows)
        return self._write_merged(con, d / HISTORY, "new", _CANDLE_COLS, source if not
                                  live.exists() else None)

    def compact(self, symbol: str, timeframe: str, keep_ms: int, min_rows: int,
                kind: str = "candles") -> int:
        """Pasa al histórico las filas vivas más viejas que `keep_ms` cuando el tramo vivo supera
        `min_rows`. Primero escribe el histórico y luego recorta el vivo: ninguna fila falta en
        ningún momento (a lo sumo está un instante en los dos, y la lectura no la duplica). Solo
        debe llamarla el proceso que escribe el tramo vivo. Devuelve las filas movidas."""
        d = self._dir(kind, symbol, timeframe)
        live = d / LIVE
        if not live.exists():
            return 0
        con = duckdb.connect()
        n, hi = con.execute(f"SELECT count(*), max(t) FROM {_rp(live)}").fetchone()
        if n <= min_rows:
            return 0
        cut = int(hi) - keep_ms
        con.execute(f"CREATE TABLE old AS SELECT {_CANDLE_COLS} FROM ({_EMPTY_CANDLES} "
                    f"UNION ALL BY NAME SELECT * FROM {_rp(live)} WHERE t < {cut})")
        moved = con.execute("SELECT count(*) FROM old").fetchone()[0]
        if not moved:
            return 0
        self._write_merged(con, d / HISTORY, "old", _CANDLE_COLS, None)
        con.execute(f"CREATE TABLE keep AS SELECT * FROM {_rp(live)} WHERE t >= {cut} ORDER BY t")
        tmp = live.with_suffix(".tmp")
        con.execute(f"COPY keep TO {_lit(tmp)} (FORMAT PARQUET)")
        _replace(tmp, live)
        return int(moved)

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
    def _write_merged(self, con, dst: Path, table: str, cols: str, source: str | None) -> int:
        """`dst` ∪ `table` (gana `table` en el mismo `t`), escrito de forma atómica."""
        if dst.exists():
            con.execute(
                f"CREATE TABLE merged AS SELECT {cols}, 1 AS pri FROM {table} UNION ALL BY NAME "
                f"SELECT *, 0 AS pri FROM {_rp(dst)}")
        else:
            con.execute(f"CREATE TABLE merged AS SELECT {cols}, 1 AS pri FROM {table}")
        con.execute(
            f"CREATE TABLE out AS SELECT {cols} FROM merged "
            f"QUALIFY row_number() OVER (PARTITION BY t ORDER BY pri DESC) = 1 ORDER BY t")
        tmp = dst.with_suffix(".tmp")
        con.execute(f"COPY out TO {_lit(tmp)} (FORMAT PARQUET)")
        _replace(tmp, dst)
        if source is not None:
            (dst.parent / "meta.json").write_text(json.dumps({"source": source}),
                                                  encoding="utf-8")
        con.execute("DROP TABLE merged")
        n = con.execute("SELECT count(*) FROM out").fetchone()[0]
        con.execute("DROP TABLE out")
        return int(n)

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
        live = self._write_merged(con, f, "new", cols, source)
        hist = f.parent / HISTORY
        return live + (int(con.execute(f"SELECT count(*) FROM {_rp(hist)}").fetchone()[0])
                       if hist.exists() else 0)

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
        src = self.sql_source(kind, symbol, timeframe, start, end)
        if src is None:
            return []
        base = f"SELECT {cols} FROM {src}"
        if last is not None:
            q = f"SELECT * FROM ({base} ORDER BY t DESC LIMIT {int(last)}) ORDER BY t"
        else:
            q = f"{base} ORDER BY t"
        return duckdb.connect().execute(q).fetchall()


def _rows(candles: list[Candle]) -> list[tuple]:
    return [(c.t, c.o, c.h, c.l, c.c, c.v, c.taker_buy_v, c.trades) for c in candles]
