"""Copia simulada (T42) en `data/leaders.duckdb` + resumen JSON para la API.

- `copy_state`: estado de cada subcuenta (saldo, posiciones, stops, pausa, kill-switch) para
  sobrevivir a reinicios del servicio.
- `copy_journal`: bitácora completa (señal, decisión, riesgo, orden, rechazo y motivo,
  stop, funding, reconciliación, pausa) con clave (líder, secuencia).
Se mezcla en `LeaderStore` (misma conexión y candado). El servicio es el único proceso que
abre la base; la API lee `data/leaders/copy_sim.json` (`write_summary`/`read_summary`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from eim.copytrading.copy_models import JournalEntry

COPY_DDL = """
CREATE TABLE IF NOT EXISTS copy_state (
    leader_id VARCHAR PRIMARY KEY, saved_at BIGINT, state VARCHAR);
CREATE TABLE IF NOT EXISTS copy_journal (
    leader_id VARCHAR, seq BIGINT, t BIGINT, kind VARCHAR, coin VARCHAR, code VARCHAR,
    text VARCHAR, data VARCHAR, PRIMARY KEY (leader_id, seq));
"""
SUMMARY = "copy_sim.json"
CONTROL = "copy_control.json"


class CopyTables:
    """Métodos de T42 sobre `LeaderStore` (usa sus `_exec` e `_insert`)."""

    def _exec(self, q: str, params: list | tuple = ()) -> list[tuple]: ...  # LeaderStore

    def _insert(self, table: str, cols: str, rows: list[tuple], chunk: int = 400) -> int: ...

    def save_copy_state(self, lid: str, saved_at: int, state: dict) -> None:
        self._exec("INSERT INTO copy_state VALUES (?, ?, ?) ON CONFLICT (leader_id) DO UPDATE "
                   "SET saved_at = excluded.saved_at, state = excluded.state",
                   [lid, saved_at, json.dumps(state, default=float)])

    def copy_states(self) -> dict[str, dict]:
        return {r[0]: json.loads(r[1])
                for r in self._exec("SELECT leader_id, state FROM copy_state")}

    def add_journal(self, entries: list[JournalEntry]) -> int:
        return self._insert(
            "copy_journal", "leader_id, seq, t, kind, coin, code, text, data",
            [(e.leader_id, e.seq, e.t, e.kind, e.coin, e.code, e.text,
              json.dumps(e.data, default=float, ensure_ascii=False)) for e in entries])

    def journal(self, lid: str | None = None, since: int = 0,
                kinds: tuple[str, ...] | None = None) -> list[JournalEntry]:
        q = ("SELECT leader_id, seq, t, kind, coin, code, text, data FROM copy_journal "
             "WHERE t >= ?")
        args: list = [since]
        if lid:
            q, args = q + " AND leader_id = ?", [*args, lid]
        if kinds:
            q += f" AND kind IN ({', '.join('?' * len(kinds))})"
            args += list(kinds)
        rows = self._exec(q + " ORDER BY leader_id, seq", args)
        return [JournalEntry(leader_id=r[0], seq=r[1], t=r[2], kind=r[3], coin=r[4], code=r[5],
                             text=r[6], data=json.loads(r[7] or "{}")) for r in rows]


def write_summary(root: str | Path, payload: dict) -> Path:
    path = Path(root) / "leaders" / SUMMARY
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, default=float, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_summary(root: str | Path) -> dict | None:
    path = Path(root) / "leaders" / SUMMARY
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def request_resume(root: str | Path, leader_ids: list[str], now: int) -> Path:
    """Pide al servicio reanudar (solo manual): lo recoge en su siguiente vuelta. Se suma a lo
    ya pedido y aún no recogido (dos pedidos seguidos no se pisan)."""
    path = Path(root) / "leaders" / CONTROL
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        prev = json.loads(path.read_text(encoding="utf-8")).get("resume") or []
    except (OSError, ValueError, AttributeError):
        prev = []
    ids = list(dict.fromkeys([*prev, *leader_ids]))
    path.write_text(json.dumps({"resume": ids, "requested_at": now}), encoding="utf-8")
    return path


def take_control(root: str | Path) -> dict | None:
    path = Path(root) / "leaders" / CONTROL
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = None
    path.unlink(missing_ok=True)
    return d
