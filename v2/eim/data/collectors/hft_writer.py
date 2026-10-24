"""Escritor de la captura HFT (T78): Parquet ZSTD por hora en `root/micro_hft/<tipo>/symbol=S/
date=D/hour=HH/part-*.parquet`.

Acumula filas por tipo y las vuelca en un hilo aparte: la escritura nunca frena el bucle que sella
la hora de recepción. La hora de la partición la decide quien añade (la captura avanza de hora una
sola vez y nunca retrocede), así un re-anclaje del reloj no deja una fila en la hora equivocada.
Las filas se convierten por columnas (pandas → DuckDB): ~30 veces más rápido que fila a fila.
"""

from __future__ import annotations

import time
from collections import Counter, deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import duckdb
import pandas as pd

from eim.data.collectors.hft_schema import AREA, HOUR_NS, columns, ddl
from eim.observability import hooks_service

COMPONENT = "data.hft_collector"


def _lit(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


def hour_dir(root: str | Path, kind: str, symbol: str, hour: int) -> Path:
    """Carpeta de la hora `hour` (horas UTC desde 1970) de `kind`."""
    tm = time.gmtime(hour * 3600)
    return (Path(root) / AREA / kind / f"symbol={symbol}" / time.strftime("date=%Y-%m-%d", tm)
            / f"hour={tm.tm_hour:02d}")


def write_rows(root: str | Path, kind: str, symbol: str, hour: int, rows: list[tuple]) -> Path:
    """Escribe `rows` como una parte nueva de la hora (escritura atómica: .tmp → .parquet)."""
    d = hour_dir(root, kind, symbol, hour)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"part-{rows[0][0]}-{rows[0][3]}-{time.time_ns()}.parquet"
    df = pd.DataFrame(rows, columns=columns(kind))
    con = duckdb.connect()
    try:
        con.execute("SET threads = 1")
        con.register("df", df)
        con.execute(f"CREATE TABLE x ({ddl(kind)})")
        con.execute("INSERT INTO x SELECT * FROM df")
        tmp = f.with_suffix(".tmp")
        con.execute(f"COPY x TO {_lit(tmp)} (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        con.close()
    tmp.replace(f)
    return f


class HftStore:
    """Buffers por (tipo, hora) y volcado cada `flush_secs` o `flush_rows`."""

    def __init__(self, root: str | Path, symbol: str, flush_secs: float = 30.0,
                 flush_rows: int = 50_000, threaded: bool = True,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.root, self.symbol = Path(root), symbol.upper()
        self.flush_secs, self.flush_rows, self._clock = flush_secs, flush_rows, clock
        self.bufs: dict[tuple[str, int], list[tuple]] = {}
        self._pool = ThreadPoolExecutor(1, thread_name_prefix="hft-writer") if threaded else None
        self._futs: deque[Future] = deque()
        self._last = clock()
        self.rows_written: Counter[str] = Counter()
        self.errors = 0
        self.last_error = ""

    def add(self, kind: str, hour: int, row: tuple) -> None:
        buf = self.bufs.setdefault((kind, hour), [])
        buf.append(row)
        if len(buf) >= self.flush_rows:
            self._submit((kind, hour))

    def maybe_flush(self) -> None:
        if self._clock() - self._last >= self.flush_secs:
            self.flush()

    def flush(self) -> None:
        self._last = self._clock()
        for key in [k for k, v in self.bufs.items() if v]:
            self._submit(key)

    @property
    def backlog(self) -> int:
        """Volcados encolados que aún no terminaron (disco lento si crece)."""
        while self._futs and self._futs[0].done():
            self._futs.popleft()
        return len(self._futs)

    def close(self) -> None:
        self.flush()
        if self._pool is not None:
            self._pool.shutdown(wait=True)

    def _submit(self, key: tuple[str, int]) -> None:
        rows = self.bufs.pop(key)
        if self._pool is None:
            self._write(key, rows)
        else:
            self._futs.append(self._pool.submit(self._write, key, rows))

    def _write(self, key: tuple[str, int], rows: list[tuple]) -> None:
        kind, hour = key
        try:
            write_rows(self.root, kind, self.symbol, hour, rows)
            self.rows_written[kind] += len(rows)
            hooks_service.beat(COMPONENT, min_interval_s=60, detail={"kind": kind,
                                                                       "rows": len(rows)})
        except Exception as e:  # noqa: BLE001 - la captura sigue; el latido lo expone
            self.errors += 1
            self.last_error = f"{kind}: {type(e).__name__}: {e}"[:300]
            hooks_service.service_error(COMPONENT, e, detail={"kind": kind, "rows": len(rows)})


def hour_of(recv_ns: int) -> int:
    return recv_ns // HOUR_NS

