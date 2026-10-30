"""Historial propio de líderes (T40) en DuckDB: `data/leaders.duckdb`.

Base aparte de `reports.duckdb`: el vigilante corre en su propio proceso y DuckDB no admite
dos procesos escribiendo el mismo archivo. Deduplicación por clave primaria:
ejecuciones (líder, tid, oid), funding (líder, moneda, t), apalancamiento (líder, moneda, t).
Las posiciones se guardan como foto solo si cambian (o cada `SNAPSHOT_KEEP_MS`).
Tablas de la evaluación (T41: cartera, precio del seguidor, veredictos) en
`leader_score_store.py`; las de la copia simulada (T42: estado y bitácora) en `copy_store.py`.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from eim.core.leaders import Leader, LeaderFill, LeaderFunding, LeaderPosition, LeaderStatus
from eim.data.copy_store import COPY_DDL, CopyTables
from eim.data.duck import tune
from eim.data.leader_score_store import SCORE_DDL, ScoreTables
from eim.data.machine import add_machine_column, machine_id
from eim.leaders.book import Gap, Recon
from eim.leaders.params import POSITIONS_MAX_AGE_MS, SNAPSHOT_KEEP_MS

DB_NAME = "leaders.duckdb"
_DDL = """
CREATE TABLE IF NOT EXISTS leaders (
    id VARCHAR PRIMARY KEY, venue VARCHAR, address VARCHAR, label VARCHAR, origin VARCHAR,
    status VARCHAR, discovered_at BIGINT, updated_at BIGINT, source VARCHAR, evidence VARCHAR);
CREATE TABLE IF NOT EXISTS leader_fills (
    leader_id VARCHAR, tid BIGINT, oid BIGINT, address VARCHAR, symbol VARCHAR, side VARCHAR,
    action VARCHAR,
    size DOUBLE, price DOUBLE, start_position DOUBLE, end_position DOUBLE, fee DOUBLE,
    fee_token VARCHAR, closed_pnl DOUBLE, crossed BOOLEAN, liquidated BOOLEAN, leverage DOUBLE,
    t BIGINT, observed_at BIGINT, channel VARCHAR, source VARCHAR,
    PRIMARY KEY (leader_id, tid, oid));
CREATE TABLE IF NOT EXISTS leader_funding (
    leader_id VARCHAR, symbol VARCHAR, t BIGINT, usdc DOUBLE, rate DOUBLE, size DOUBLE,
    observed_at BIGINT, source VARCHAR, PRIMARY KEY (leader_id, symbol, t));
CREATE TABLE IF NOT EXISTS leader_leverage (
    leader_id VARCHAR, symbol VARCHAR, t BIGINT, observed_at BIGINT, old DOUBLE, new DOUBLE,
    old_mode VARCHAR, new_mode VARCHAR, PRIMARY KEY (leader_id, symbol, t));
CREATE TABLE IF NOT EXISTS leader_positions (
    leader_id VARCHAR, t BIGINT, observed_at BIGINT, positions VARCHAR,
    PRIMARY KEY (leader_id, observed_at));
CREATE TABLE IF NOT EXISTS leader_recon (
    leader_id VARCHAR, t BIGINT, observed_at BIGINT, checked INTEGER, skipped INTEGER,
    size_ok BOOLEAN, match BOOLEAN, resynced BOOLEAN, diffs VARCHAR, clock_offset_ms INTEGER,
    retries INTEGER, machine VARCHAR);
CREATE TABLE IF NOT EXISTS leader_gaps (
    leader_id VARCHAR, symbol VARCHAR, t_from BIGINT, t_to BIGINT, cause VARCHAR,
    detail VARCHAR, observed_at BIGINT, recovered INTEGER, machine VARCHAR);
"""
_MACHINE_TABLES = ("leader_recon", "leader_gaps")     # sin clave natural: T61 les añade `machine`
_FILL_COLS = ("leader_id, tid, oid, address, symbol, side, action, size, price, start_position, "
              "end_position, fee, fee_token, closed_pnl, crossed, liquidated, leverage, t, "
              "observed_at, channel, source")


def _shape(positions: list[LeaderPosition]) -> list[tuple]:
    """Lo que define la posición (sin PnL ni margen, que cambian con el precio)."""
    return sorted((p.symbol, p.side, p.size, p.entry, p.leverage, p.margin_mode)
                  for p in positions)


class LeaderStore(ScoreTables, CopyTables):
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(self.path)
        tune(self._con)  # sin tope, DuckDB toma el 80 % de la RAM (12,5 de 16 GB)
        self._con.execute(_DDL + SCORE_DDL + COPY_DDL)
        self._lock = threading.Lock()
        self.machine = "local" if self.path == ":memory:" else machine_id(Path(self.path).parent)
        for t in _MACHINE_TABLES:       # bases previas a T61: rellena con el id local
            add_machine_column(self._con, t, self.machine)

    @classmethod
    def at_root(cls, root: str | Path) -> LeaderStore:
        return cls(Path(root) / DB_NAME)

    def close(self) -> None:
        with self._lock:
            self._con.close()

    @property
    def connection(self):
        """(conexión, cerrojo) para la experiencia compartida (T61, `eim.data.share_auto`)."""
        return self._con, self._lock

    @contextmanager
    def reader(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Cursor propio en una transacción de lectura: instantánea coherente de DuckDB que no
        toma el candado, así la captura (bucle del WS) sigue escribiendo mientras se lee en tandas
        (evaluación incremental, `leader_fold_io.py`)."""
        with self._lock:
            cur = self._con.cursor()
        try:
            cur.execute("BEGIN TRANSACTION")
            yield cur
        finally:
            try:
                cur.execute("ROLLBACK")
            finally:
                cur.close()

    def _exec(self, q: str, params: list | tuple = ()) -> list[tuple]:
        with self._lock:
            return self._con.execute(q, params).fetchall()

    def _insert(self, table: str, cols: str, rows: list[tuple], chunk: int = 400) -> int:
        """INSERT OR IGNORE por clave primaria; devuelve cuántas filas eran nuevas. VALUES
        multifila por lotes: `executemany` de DuckDB es ~25× más lento."""
        n = 0
        one = "(" + ", ".join("?" * len(rows[0])) + ")" if rows else ""
        with self._lock:
            for k in range(0, len(rows), chunk):
                part = rows[k:k + chunk]
                q = f"INSERT OR IGNORE INTO {table} ({cols}) VALUES " + ", ".join([one] * len(part))
                n += self._con.execute(q, [x for r in part for x in r]).fetchone()[0]
        return n

    # --- registro de líderes -----------------------------------------------------------------
    def upsert_leader(self, ld: Leader, now: int) -> bool:
        """Alta (True) o actualización de etiqueta/evidencia (si vienen vacías se conservan);
        no pisa el estado ni la fecha de alta."""
        new = not self._exec("SELECT 1 FROM leaders WHERE id = ?", [ld.id])
        self._exec(
            "INSERT INTO leaders VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT (id) DO UPDATE SET "
            "label = CASE WHEN excluded.label <> '' THEN excluded.label ELSE leaders.label END, "
            "evidence = CASE WHEN excluded.evidence <> '{}' THEN excluded.evidence "
            "ELSE leaders.evidence END, updated_at = excluded.updated_at",
            [ld.id, ld.venue, ld.address, ld.label, ld.origin, ld.status, ld.discovered_at, now,
             ld.source, json.dumps(ld.evidence, ensure_ascii=False)])
        return new

    def set_status(self, lid: str, status: LeaderStatus, now: int) -> bool:
        if not self._exec("SELECT 1 FROM leaders WHERE id = ?", [lid]):
            return False
        self._exec("UPDATE leaders SET status = ?, updated_at = ? WHERE id = ?", [status, now, lid])
        return True

    def leaders(self, statuses: tuple[str, ...] | None = None) -> list[Leader]:
        q = ("SELECT id, venue, address, label, origin, status, discovered_at, source, evidence "
             "FROM leaders")
        params: list = []
        if statuses:
            q += f" WHERE status IN ({', '.join('?' * len(statuses))})"
            params = list(statuses)
        rows = self._exec(q + " ORDER BY discovered_at, id", params)
        return [Leader(id=r[0], venue=r[1], address=r[2], label=r[3], origin=r[4], status=r[5],
                       discovered_at=r[6], source=r[7], evidence=json.loads(r[8] or "{}"))
                for r in rows]

    # --- historial ---------------------------------------------------------------------------
    def add_fills(self, fills: list[LeaderFill]) -> int:
        rows = [(f.leader_id, f.tid, f.oid, f.address, f.symbol, f.side, f.action, f.size, f.price,
                 f.start_position, f.end_position, f.fee, f.fee_token, f.closed_pnl, f.crossed,
                 f.liquidated, f.leverage, f.t, f.observed_at, f.channel, f.source)
                for f in fills]
        return self._insert("leader_fills", _FILL_COLS, rows)

    def add_funding(self, rows: list[LeaderFunding]) -> int:
        return self._insert(
            "leader_funding", "leader_id, symbol, t, usdc, rate, size, observed_at, source",
            [(r.leader_id, r.symbol, r.t, r.usdc, r.rate, r.size, r.observed_at, r.source)
             for r in rows])

    def add_leverage(self, lid: str, recon: Recon, observed_at: int) -> int:
        return self._insert(
            "leader_leverage", "leader_id, symbol, t, observed_at, old, new, old_mode, new_mode",
            [(lid, c.symbol, recon.t, observed_at, c.old, c.new, c.old_mode, c.new_mode)
             for c in recon.leverage])

    def last_fill_t(self, lid: str) -> int | None:
        return self._exec("SELECT max(t) FROM leader_fills WHERE leader_id = ?", [lid])[0][0]

    def last_funding_t(self, lid: str) -> int | None:
        return self._exec("SELECT max(t) FROM leader_funding WHERE leader_id = ?", [lid])[0][0]

    def fills(self, lid: str, start: int | None = None, end: int | None = None
              ) -> list[LeaderFill]:
        rows = self._exec(f"SELECT {_FILL_COLS} FROM leader_fills WHERE leader_id = ? "
                          "AND t >= ? AND t < ? ORDER BY t, observed_at",
                          [lid, start or 0, end or 2**62])
        keys = [c.strip() for c in _FILL_COLS.split(",")]
        return [LeaderFill(**dict(zip(keys, r, strict=True))) for r in rows]

    def history(self, lid: str, start: int | None = None, end: int | None = None
                ) -> list[dict]:
        """Eventos en orden: apertura/aumento/reducción/cierre/giro (con comisión y PnL
        cerrado), funding y cambios de apalancamiento."""
        out: list[dict] = [{"kind": f.action, "t": f.t, "symbol": f.symbol, "side": f.side,
                            "size": f.size, "price": f.price, "position": f.end_position,
                            "fee": f.fee, "closed_pnl": f.closed_pnl, "liquidated": f.liquidated,
                            "observed_at": f.observed_at, "channel": f.channel}
                           for f in self.fills(lid, start, end)]
        lo, hi = start or 0, end or 2**62
        for sym, t, usdc, rate, size, obs in self._exec(
                "SELECT symbol, t, usdc, rate, size, observed_at FROM leader_funding "
                "WHERE leader_id = ? AND t >= ? AND t < ?", [lid, lo, hi]):
            out.append({"kind": "funding", "t": t, "symbol": sym, "usdc": usdc, "rate": rate,
                        "position": size, "observed_at": obs})
        for sym, t, obs, old, new, om, nm in self._exec(
                "SELECT symbol, t, observed_at, old, new, old_mode, new_mode FROM "
                "leader_leverage WHERE leader_id = ? AND t >= ? AND t < ?", [lid, lo, hi]):
            out.append({"kind": "leverage", "t": t, "symbol": sym, "old": old, "new": new,
                        "old_mode": om, "new_mode": nm, "observed_at": obs})
        return sorted(out, key=lambda e: (e["t"], e["observed_at"]))

    # --- posiciones --------------------------------------------------------------------------
    def save_positions(self, lid: str, t: int, observed_at: int,
                       positions: list[LeaderPosition], keep_ms: int = SNAPSHOT_KEEP_MS) -> bool:
        last = self._exec("SELECT observed_at, positions FROM leader_positions WHERE "
                          "leader_id = ? ORDER BY observed_at DESC LIMIT 1", [lid])
        if last and observed_at - last[0][0] < keep_ms:
            prev = [LeaderPosition.model_validate(p) for p in json.loads(last[0][1])]
            if _shape(prev) == _shape(positions):
                return False
        payload = json.dumps([p.model_dump() for p in positions])
        return self._insert("leader_positions", "leader_id, t, observed_at, positions",
                            [(lid, t, observed_at, payload)]) == 1

    def positions_at(self, asof: int, statuses: tuple[str, ...] = ("approved",),
                     max_age_ms: int = POSITIONS_MAX_AGE_MS) -> list[LeaderPosition]:
        """Posiciones vigentes a `asof` (nunca posteriores) de los líderes con ese estado."""
        ids = [ld.id for ld in self.leaders(statuses)]
        out: list[LeaderPosition] = []
        for lid in ids:
            row = self._exec("SELECT observed_at, positions FROM leader_positions WHERE "
                             "leader_id = ? AND observed_at <= ? ORDER BY observed_at DESC "
                             "LIMIT 1", [lid, asof])
            if row and asof - row[0][0] <= max_age_ms:
                out += [LeaderPosition.model_validate(p) for p in json.loads(row[0][1])]
        return out

    # --- control de calidad ------------------------------------------------------------------
    def add_recon(self, lid: str, recon: Recon, observed_at: int, resynced: bool,
                  clock_offset_ms: int = 0, retries: int = 0) -> None:
        diffs = json.dumps([d.__dict__ for d in recon.diffs]) if recon.diffs else None
        self._exec("INSERT INTO leader_recon VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   [lid, recon.t, observed_at, len(recon.checked), len(recon.skipped),
                    recon.size_ok, recon.match, resynced, diffs, clock_offset_ms, retries,
                    self.machine])

    def add_gap(self, gap: Gap, observed_at: int, recovered: int) -> None:
        self._exec("INSERT INTO leader_gaps VALUES (?,?,?,?,?,?,?,?,?)",
                   [gap.leader_id, gap.symbol, gap.start, gap.end, gap.cause, gap.detail,
                    observed_at, recovered, self.machine])

    def query(self, q: str, params: list | tuple = ()) -> list[tuple]:
        """Lectura libre (informes de `eim.leaders.report`)."""
        return self._exec(q, params)

    def snapshot(self, path: str | Path) -> Path:
        """Copia coherente de toda la base en `path` (T42: reproducción con el servicio en
        marcha, que es el único proceso que puede abrir el archivo). Corre en un cursor propio
        (transacción aparte de DuckDB) y no toma el candado: la captura sigue escribiendo
        mientras se copia."""
        dst = Path(path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.stem + ".tmp.duckdb")
        tmp.unlink(missing_ok=True)
        with self._lock:
            cur = self._con.cursor()
        try:
            src = cur.execute("SELECT current_database()").fetchone()[0]
            alias = "snap_" + "".join(ch if ch.isalnum() else "_" for ch in dst.stem)
            lit = str(tmp).replace("'", "''")  # ATTACH no admite parámetros
            cur.execute(f"ATTACH '{lit}' AS {alias}")
            try:
                cur.execute(f'COPY FROM DATABASE "{src}" TO {alias}')
            finally:
                cur.execute(f"DETACH {alias}")
        finally:
            cur.close()
        tmp.replace(dst)
        return dst

