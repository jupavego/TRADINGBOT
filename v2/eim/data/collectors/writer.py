"""Escritor Parquet por hora: `root/micro/<kind>/symbol=S/date=D/hour=HH/part-*.parquet`."""

from __future__ import annotations

import time
from pathlib import Path

import duckdb

SCHEMAS = {
    "trades": "t BIGINT, id BIGINT, p DOUBLE, q DOUBLE, maker BOOLEAN",  # maker = vendedor agresor
    "top": "t BIGINT, bid_p DOUBLE, bid_q DOUBLE, ask_p DOUBLE, ask_q DOUBLE, "
           "bids VARCHAR, asks VARCHAR",
    "depth": "t BIGINT, first_id BIGINT, last_id BIGINT, prev_id BIGINT, side VARCHAR, "
             "p DOUBLE, q DOUBLE",
    "gaps": "t BIGINT, stream VARCHAR, detail VARCHAR",
}


def _lit(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


class HourlyWriter:
    """Acumula filas y las vuelca por hora (columna `t` en ms). `flush()` al cerrar."""

    def __init__(self, root: str | Path, kind: str, symbol: str,
                 flush_rows: int = 5000, flush_secs: float = 30.0) -> None:
        self.base = Path(root) / "micro" / kind / f"symbol={symbol}"
        self.schema = SCHEMAS[kind]
        self.flush_rows, self.flush_secs = flush_rows, flush_secs
        self.buf: list[tuple] = []
        self._last = time.monotonic()
        self._seq = 0

    def add(self, row: tuple) -> None:
        self.buf.append(row)
        if len(self.buf) >= self.flush_rows or time.monotonic() - self._last >= self.flush_secs:
            self.flush()

    def flush(self) -> None:
        self._last = time.monotonic()
        if not self.buf:
            return
        by_hour: dict[int, list[tuple]] = {}
        for row in self.buf:
            by_hour.setdefault(row[0] // 3_600_000, []).append(row)
        self.buf = []
        for hour, rows in by_hour.items():
            tm = time.gmtime(hour * 3600)
            d = self.base / time.strftime("date=%Y-%m-%d", tm) / f"hour={tm.tm_hour:02d}"
            d.mkdir(parents=True, exist_ok=True)
            self._seq += 1
            f = d / f"part-{rows[0][0]}-{self._seq}-{time.time_ns()}.parquet"
            con = duckdb.connect()
            con.execute(f"CREATE TABLE x ({self.schema})")
            con.executemany(f"INSERT INTO x VALUES ({', '.join('?' * len(rows[0]))})", rows)
            tmp = f.with_suffix(".tmp")
            con.execute(f"COPY x TO {_lit(tmp)} (FORMAT PARQUET)")
            tmp.replace(f)
            con.close()
