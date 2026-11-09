"""Instantáneas de datos versionadas (T124): qué datos vio un resultado, fijado e inmutable.

Una instantánea es una serie del almacén (velas de un símbolo y marco, más el funding del
símbolo) cortada en `[start, end)`: solo velas **cerradas** a `end` (`t + paso ≤ end`) y funding
con `t < end`. Su identidad vive en la tabla `data_snapshots` de `snapshots/snapshots.duckdb`:
rango, nº de velas, huecos, hash del contenido, momento de creación, proveedor y versión del
formato. El id sale de la serie, el rango, el modo y ese hash, así que la misma petición sobre
los mismos datos da el mismo id y otros datos dan otro: **una instantánea no se reescribe, se
crea otra**.

- **congelada**: además guarda una copia Parquet en `snapshots/frozen/<id>/` para poder
  recalcular aunque el almacén cambie después (backtest, calibración, puerta de edge).
- **ligera**: solo identidad y hash (puntuación de bots, que se recalcula cada 4 h): si el
  almacén cambia se detecta, pero la cifra vieja ya no se puede reconstruir.

`SnapshotView` es la única forma de leer una instantánea como si fuera el almacén y corta en su
fecha: pedir una vela posterior a `end` lanza `LookaheadError`. Idea tomada de ArcticDB (Man
Group) sobre DuckDB + Parquet; ArcticDB no se instala por su licencia, BSL 1.1
(docs/OPERACION.md §4, «Instantáneas de datos»).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

import duckdb

from eim.core import Candle
from eim.data.snapshot_view import LookaheadError, SnapshotScopeError, SnapshotView
from eim.data.timeframes import tf_ms

VERSION = 1                      # formato de la instantánea (entra en el hash del id)
DIR, DB = "snapshots", "snapshots.duckdb"
LOCK_WAIT_S = 15.0               # otro proceso con la base abierta: se reintenta hasta aquí
_COLS = ("t", "o", "h", "l", "c", "v", "taker_buy_v", "trades")
FUNDING = "funding"              # instantánea solo de funding (marco "-")
_DDL = """
CREATE TABLE IF NOT EXISTS data_snapshots (
    id VARCHAR PRIMARY KEY, kind VARCHAR, symbol VARCHAR, timeframe VARCHAR,
    start_ms BIGINT, end_ms BIGINT, first_t BIGINT, last_t BIGINT, n_candles BIGINT,
    n_funding BIGINT, gaps BIGINT, content_hash VARCHAR, created_ms BIGINT, source VARCHAR,
    funding_source VARCHAR, version INTEGER, frozen BOOLEAN, origin VARCHAR, store_dir VARCHAR
)"""


class SnapshotCorrupt(ValueError):
    """La copia congelada ya no da el hash con que se registró (alterada o dañada)."""


@dataclass(frozen=True)
class SnapshotInfo:
    id: str
    kind: str
    symbol: str
    timeframe: str
    start_ms: int
    end_ms: int
    first_t: int | None
    last_t: int | None
    n_candles: int
    n_funding: int
    gaps: int
    content_hash: str
    created_ms: int
    source: str
    funding_source: str
    version: int
    frozen: bool
    origin: str
    store_dir: str = ""      # almacén del que se leyó, relativo a la carpeta de instantáneas

    def coverage(self) -> dict:
        """Cobertura real: lo que hay frente a lo que cabría en el rango sin huecos."""
        exp = ((self.last_t - self.first_t) // tf_ms(self.timeframe) + 1
               if self.n_candles and self.kind != FUNDING else 0)
        return {"first_t": self.first_t, "last_t": self.last_t, "candles": self.n_candles,
                "expected": exp, "gaps": self.gaps, "funding": self.n_funding}

    def as_dict(self) -> dict:
        return {**asdict(self), "coverage": self.coverage()}


@dataclass(frozen=True)
class Snapshot:
    info: SnapshotInfo
    candles: list[Candle] = field(repr=False)
    funding: list[tuple[int, float]] = field(repr=False)

    def view(self) -> SnapshotView:
        return SnapshotView(self)


__all__ = ["LookaheadError", "Snapshot", "SnapshotCorrupt", "SnapshotInfo", "SnapshotScopeError",
           "SnapshotStore", "SnapshotView", "content_hash", "read_range", "snapshot_id"]


def content_hash(candles: list[Candle], funding: list[tuple[int, float]]) -> str:
    """SHA-256 del contenido canónico (repr exacto de cada número; None = vacío)."""
    h = hashlib.sha256(f"eim-snapshot-v{VERSION}\n".encode())
    for c in candles:
        h.update(",".join("" if v is None else repr(v) for v in (
            c.t, c.o, c.h, c.l, c.c, c.v, c.taker_buy_v, c.trades)).encode() + b"\n")
    for t, x in funding:
        h.update(f"f{t!r},{x!r}\n".encode())
    return h.hexdigest()


def snapshot_id(kind: str, symbol: str, tf: str, start: int, end: int, chash: str,
                frozen: bool) -> str:
    key = f"{kind}|{symbol}|{tf}|{start}|{end}|{chash}|{'f' if frozen else 'l'}|{VERSION}"
    return "ds_" + hashlib.sha256(key.encode()).hexdigest()[:16]


def read_range(store, kind: str, symbol: str, tf: str, start: int | None, end: int,
               funding: bool = True) -> tuple[list[Candle], list[tuple[int, float]]]:
    """Lo que el almacén tiene HOY en el rango, con el mismo corte que una instantánea."""
    candles = [] if kind == FUNDING else store.read_candles(
        symbol, tf, start=start, end=end - tf_ms(tf) + 1, kind=kind)
    lo = start if start is not None else (candles[0].t if candles else end)
    rows = store.read_series("funding", symbol, start=lo, end=end) if funding else []
    return candles, rows


def _gaps(candles: list[Candle], step: int) -> int:
    return sum(1 for a, b in zip(candles, candles[1:], strict=False) if b.t - a.t > step)


class SnapshotStore:
    """`root/snapshots/snapshots.duckdb` (tabla `data_snapshots`) + `root/snapshots/frozen/`."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.dir = self.root / DIR
        self.db = self.dir / DB

    @contextmanager
    def connect(self, read_only: bool = False):
        """Abre la base solo lo que dura la operación: varios procesos (API, CLI) la comparten."""
        self.dir.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                con = duckdb.connect(str(self.db), read_only=read_only and self.db.exists())
                break
            except duckdb.IOException:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)
        try:
            if not read_only or not self.db.exists():
                con.execute(_DDL)
            yield con
        finally:
            con.close()

    # --- crear ------------------------------------------------------------
    def create(self, store, symbol: str, timeframe: str, start: int | None = None,
               end: int | None = None, kind: str = "candles", funding: bool = True,
               freeze: bool = True, origin: str = "") -> Snapshot:
        """Fija lo que el almacén tiene ahora en `[start, end)` (por defecto, toda la historia
        cerrada hasta ahora)."""
        end = int(end if end is not None else time.time() * 1000)
        candles, rows = read_range(store, kind, symbol, timeframe, start, end, funding)
        first = candles[0].t if candles else (rows[0][0] if rows else end)
        lo = int(start if start is not None else first)
        fsrc = (store.source(FUNDING, symbol) or "desconocida") if funding else ""
        src = fsrc if kind == FUNDING else store.source(kind, symbol, timeframe) or "desconocida"
        return self.register(kind, symbol, timeframe, lo, end, candles, rows, src, fsrc, freeze,
                             origin, self._rel(getattr(store, "root", None)))

    def _rel(self, path) -> str:
        """Almacén de origen relativo a esta carpeta (sirve igual en otro equipo)."""
        if path is None:
            return ""
        try:
            return os.path.relpath(Path(path).resolve(), self.root.resolve())
        except ValueError:          # otra unidad (Windows): ruta absoluta
            return str(Path(path).resolve())

    def register(self, kind: str, symbol: str, timeframe: str, start: int, end: int,
                 candles: list[Candle], funding: list[tuple[int, float]], source: str,
                 funding_source: str = "", freeze: bool = True, origin: str = "",
                 store_dir: str = "") -> Snapshot:
        """Registra datos ya leídos. Si la misma instantánea existe se devuelve tal cual.
        `funding_source` vacío = la instantánea no incluye funding."""
        step = 0 if kind == FUNDING else tf_ms(timeframe)
        candles = [c for c in candles if kind != FUNDING and start <= c.t and c.t + step <= end]
        funding = [(int(t), float(x)) for t, x in funding if start <= t < end]
        chash = content_hash(candles, funding)
        sid = snapshot_id(kind, symbol, timeframe, start, end, chash, freeze)
        got = self.get(sid)
        if got is not None:
            return Snapshot(got, candles, funding)
        info = SnapshotInfo(
            sid, kind, symbol, timeframe, int(start), int(end),
            candles[0].t if candles else None, candles[-1].t if candles else None,
            len(candles), len(funding), _gaps(candles, step), chash, int(time.time() * 1000),
            source, funding_source, VERSION, freeze, origin, store_dir)
        if freeze:
            self._freeze(info, candles, funding)
        with self.connect() as con:
            con.execute("INSERT INTO data_snapshots VALUES "
                        f"({', '.join('?' * len(_DDL_FIELDS))}) ON CONFLICT DO NOTHING",
                        [getattr(info, f) for f in _DDL_FIELDS])
        return Snapshot(info, candles, funding)

    def _freeze(self, info: SnapshotInfo, candles: list[Candle],
                funding: list[tuple[int, float]]) -> None:
        dst = self.dir / "frozen" / info.id
        if dst.exists():
            return
        tmp = dst.with_name(f"{info.id}.tmp{os.getpid()}")
        tmp.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect()
        con.execute("CREATE TABLE c (t BIGINT, o DOUBLE, h DOUBLE, l DOUBLE, c DOUBLE, "
                    "v DOUBLE, taker_buy_v DOUBLE, trades BIGINT)")
        if candles:
            con.executemany("INSERT INTO c VALUES (?,?,?,?,?,?,?,?)",
                            [tuple(getattr(x, k) for k in _COLS) for x in candles])
        con.execute("CREATE TABLE f (t BIGINT, x DOUBLE)")
        if funding:
            con.executemany("INSERT INTO f VALUES (?,?)", funding)
        for name, tab in (("candles", "c"), ("funding", "f")):
            p = (tmp / f"{name}.parquet").as_posix().replace("'", "''")
            con.execute(f"COPY (SELECT * FROM {tab} ORDER BY t) TO '{p}' (FORMAT PARQUET)")
        con.close()
        (tmp / "info.json").write_text(json.dumps(asdict(info), indent=1), encoding="utf-8")
        try:
            tmp.replace(dst)
        except OSError:            # otro proceso la congeló a la vez: vale la suya (mismo hash)
            shutil.rmtree(tmp, ignore_errors=True)

    # --- leer -------------------------------------------------------------
    def get(self, sid: str) -> SnapshotInfo | None:
        if not self.db.exists():
            return None
        with self.connect(read_only=True) as con:
            row = con.execute(f"SELECT {', '.join(_DDL_FIELDS)} FROM data_snapshots WHERE id = ?",
                              [sid]).fetchone()
        return None if row is None else SnapshotInfo(*row)

    def list(self, symbol: str | None = None, limit: int = 100) -> list[SnapshotInfo]:
        if not self.db.exists():
            return []
        q = f"SELECT {', '.join(_DDL_FIELDS)} FROM data_snapshots"
        args: list = []
        if symbol:
            q, args = q + " WHERE symbol = ?", [symbol]
        with self.connect(read_only=True) as con:
            rows = con.execute(q + " ORDER BY created_ms DESC LIMIT ?", [*args, limit]).fetchall()
        return [SnapshotInfo(*r) for r in rows]

    def load(self, sid: str) -> Snapshot:
        """Copia congelada, comprobada contra su hash (`SnapshotCorrupt` si no coincide)."""
        info = self.get(sid)
        if info is None:
            raise KeyError(f"instantánea desconocida: {sid}")
        if not info.frozen:
            raise SnapshotScopeError(f"{sid} es ligera: no guarda copia de los datos")
        d = self.dir / "frozen" / sid
        if not (d / "candles.parquet").exists():
            raise SnapshotCorrupt(f"{sid}: falta la copia congelada en {d}")
        con = duckdb.connect()
        rows = con.execute(f"SELECT {', '.join(_COLS)} FROM read_parquet("
                           f"'{(d / 'candles.parquet').as_posix()}') ORDER BY t").fetchall()
        fund = con.execute("SELECT t, x FROM read_parquet("
                           f"'{(d / 'funding.parquet').as_posix()}') ORDER BY t").fetchall()
        con.close()
        candles = [Candle(t=int(t), o=o, h=h, l=lo, c=c, v=v, taker_buy_v=tb,
                          trades=None if n is None else int(n))
                   for t, o, h, lo, c, v, tb, n in rows]
        funding = [(int(t), float(x)) for t, x in fund]
        got = content_hash(candles, funding)
        if got != info.content_hash:
            raise SnapshotCorrupt(f"{sid}: la copia congelada da {got[:16]}…, se registró "
                                  f"{info.content_hash[:16]}… (alterada o dañada)")
        return Snapshot(info, candles, funding)

    def live(self, store, info: SnapshotInfo) -> Snapshot:
        """Lo que el almacén tiene hoy en el rango de la instantánea (para comparar)."""
        c, f = read_range(store, info.kind, info.symbol, info.timeframe, info.start_ms,
                          info.end_ms, funding=bool(info.funding_source))
        return Snapshot(info, c, f)


_DDL_FIELDS = tuple(SnapshotInfo.__dataclass_fields__)
