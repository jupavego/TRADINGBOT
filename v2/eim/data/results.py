"""Registro de resultados reproducibles (T124): qué cifra salió, de qué datos, código y parámetros.

Dos tablas en la base de las instantáneas (`snapshots/snapshots.duckdb`), solo se añaden:
- `data_results`: un resultado (una ventana de la puerta de edge, un backtest, una calibración,
  una puntuación de bots) con los ids de sus instantáneas, los parámetros usados, la huella del
  código y las cifras. El id sale del contenido: registrar dos veces lo mismo no duplica.
- `repro_checks`: cada `repetir` (veredicto, causas y detalle), para ver su historia.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from eim.data.snapshots import SnapshotStore

_DDL = """
CREATE TABLE IF NOT EXISTS data_results (
    id VARCHAR PRIMARY KEY, kind VARCHAR, name VARCHAR, created_ms BIGINT, snapshots VARCHAR,
    params VARCHAR, code VARCHAR, figures VARCHAR, report VARCHAR, note VARCHAR
);
CREATE TABLE IF NOT EXISTS repro_checks (
    result_id VARCHAR, checked_ms BIGINT, verdict VARCHAR, causes VARCHAR, detail VARCHAR
)"""
_FIELDS = ("id", "kind", "name", "created_ms", "snapshots", "params", "code", "figures", "report",
           "note")
_JSON = {"snapshots", "params", "code", "figures"}


def _dump(x) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class ResultRecord:
    id: str
    kind: str
    name: str
    created_ms: int
    snapshots: list[str]
    params: dict
    code: dict
    figures: dict
    report: str
    note: str


def result_id(kind: str, name: str, snapshots: list[str], params: dict, figures: dict) -> str:
    key = _dump([kind, name, snapshots, params, figures])
    return "rs_" + hashlib.sha256(key.encode()).hexdigest()[:16]


class ResultStore:
    def __init__(self, root: str | Path) -> None:
        self.snaps = SnapshotStore(root)

    def _con(self, read_only: bool = False):
        return self.snaps.connect(read_only=read_only)

    def _ready(self, con) -> None:
        con.execute(_DDL)

    def register(self, kind: str, name: str, snapshots: list[str], params: dict, code: dict,
                 figures: dict, report: str = "", note: str = "") -> ResultRecord:
        rid = result_id(kind, name, snapshots, params, figures)
        rec = ResultRecord(rid, kind, name, int(time.time() * 1000), list(snapshots), params,
                           code, figures, report, note)
        with self._con() as con:
            self._ready(con)
            con.execute("INSERT INTO data_results VALUES (?,?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT DO NOTHING",
                        [_dump(v) if k in _JSON else v for k, v in zip(
                            _FIELDS, (rec.id, rec.kind, rec.name, rec.created_ms, rec.snapshots,
                                      rec.params, rec.code, rec.figures, rec.report, rec.note),
                            strict=True)])
        return self.get(rid) or rec

    def _rows(self, where: str = "", args: list | None = None, limit: int = 200) -> list[tuple]:
        if not self.snaps.db.exists():
            return []
        with self._con() as con:
            self._ready(con)
            return con.execute(f"SELECT {', '.join(_FIELDS)} FROM data_results {where} "
                               "ORDER BY created_ms DESC LIMIT ?", [*(args or []), limit]
                               ).fetchall()

    @staticmethod
    def _rec(row: tuple) -> ResultRecord:
        return ResultRecord(*[json.loads(v) if k in _JSON else v
                              for k, v in zip(_FIELDS, row, strict=True)])

    def get(self, rid: str) -> ResultRecord | None:
        rows = self._rows("WHERE id = ?", [rid], 1)
        return self._rec(rows[0]) if rows else None

    def list(self, kind: str | None = None, limit: int = 200) -> list[ResultRecord]:
        rows = self._rows("WHERE kind = ?", [kind], limit) if kind else self._rows(limit=limit)
        return [self._rec(r) for r in rows]

    def using(self, snapshot_ids: set[str]) -> list[ResultRecord]:
        """Resultados que declaran alguna de estas instantáneas."""
        return [r for r in self.list(limit=100_000) if snapshot_ids & set(r.snapshots)]

    def add_check(self, rid: str, verdict: str, causes: list[str], detail: dict) -> None:
        with self._con() as con:
            self._ready(con)
            con.execute("INSERT INTO repro_checks VALUES (?,?,?,?,?)",
                        [rid, int(time.time() * 1000), verdict, _dump(causes), _dump(detail)])

    def checks(self, rid: str, limit: int = 20) -> list[dict]:
        if not self.snaps.db.exists():
            return []
        with self._con() as con:
            self._ready(con)
            rows = con.execute("SELECT checked_ms, verdict, causes FROM repro_checks "
                               "WHERE result_id = ? ORDER BY checked_ms DESC LIMIT ?",
                               [rid, limit]).fetchall()
        return [{"checked_ms": int(t), "verdict": v, "causes": json.loads(c)}
                for t, v, c in rows]
