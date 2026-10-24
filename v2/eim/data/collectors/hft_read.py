"""Lectura de la captura HFT (T78) por hora: base común del control de calidad y del conversor.

Las horas son horas UTC absolutas (`recv_ns // HOUR_NS`), las mismas de las particiones. Cada
lectura devuelve un `DataFrame` ordenado por (`run`, `seq`): el orden en que el recolector procesó
los mensajes, que es el que reproduce su libro.
"""

from __future__ import annotations

import calendar
import time
from pathlib import Path

import duckdb
import pandas as pd

from eim.data.collectors.hft_schema import AREA, KINDS, columns
from eim.data.collectors.hft_writer import hour_dir


def _q(path: Path | str) -> str:
    return "'" + Path(path).as_posix().replace("'", "''") + "'"


def hour_label(hour: int) -> str:
    return time.strftime("%Y-%m-%dT%H", time.gmtime(hour * 3600))


def parse_hour(label: str) -> int:
    """`2026-10-24T03` → hora UTC absoluta."""
    return calendar.timegm(time.strptime(label, "%Y-%m-%dT%H")) // 3600


def hours_with_data(root: str | Path, symbol: str, kinds: tuple[str, ...] = KINDS) -> list[int]:
    """Horas con al menos una parte de alguna de `kinds` (por defecto, cualquier tabla)."""
    out: set[int] = set()
    for kind in kinds:
        for d in (Path(root) / AREA / kind / f"symbol={symbol}").glob("date=*/hour=*"):
            if any(d.glob("part-*.parquet")):
                day = time.strptime(d.parent.name.removeprefix("date="), "%Y-%m-%d")
                out.add(calendar.timegm(day) // 3600 + int(d.name.removeprefix("hour=")))
    return sorted(out)


def read_hour(root: str | Path, symbol: str, kind: str, hour: int,
              cols: str | None = None) -> pd.DataFrame:
    """Filas de `kind` de la hora, ordenadas por (run, seq). Vacío si no hay partes."""
    d = hour_dir(root, kind, symbol, hour)
    parts = sorted(d.glob("part-*.parquet")) if d.exists() else []
    if not parts:
        return pd.DataFrame(columns=cols.replace(" ", "").split(",") if cols else columns(kind))
    lst = "[" + ", ".join(_q(p) for p in parts) + "]"
    con = duckdb.connect()
    try:
        con.execute("SET threads = 2")
        return con.execute(f"SELECT {cols or '*'} FROM read_parquet({lst}, union_by_name = true, "
                           "hive_partitioning = false) "
                           "ORDER BY run, seq").df()
    finally:
        con.close()


def tail_row(root: str | Path, symbol: str, kind: str, hour: int, cols: str) -> dict | None:
    """Última fila (por run, seq) de `kind` en la hora: enlaza una hora con la anterior."""
    d = hour_dir(root, kind, symbol, hour)
    parts = sorted(d.glob("part-*.parquet")) if d.exists() else []
    if not parts:
        return None
    lst = "[" + ", ".join(_q(p) for p in parts) + "]"
    con = duckdb.connect()
    try:
        df = con.execute(f"SELECT {cols} FROM read_parquet({lst}, union_by_name = true, "
                         "hive_partitioning = false) ORDER BY run DESC, seq DESC LIMIT 1").df()
    finally:
        con.close()
    return None if df.empty else df.iloc[0].to_dict()
