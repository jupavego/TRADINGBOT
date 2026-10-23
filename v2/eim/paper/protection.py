"""Diario de la protección progresiva (T110): el estado de cada operación con escalera, de solo
adición, en `data/paper.duckdb`.

El libro se recalcula en cada consulta (a propósito: reglas y costos vigentes) y el libro fijo
(`ledger.py`) solo guarda los cierres. Este diario guarda lo que el motor SOSTUVO en vivo mientras
la operación estaba abierta: una fila al abrirla, una por cada cambio del stop (escalón, BE+ o
recuperación) y una al cerrarla. Nunca se reescribe una fila (`INSERT`, clave `op_id|seq`); la de
mayor `seq` de cada operación es su estado vigente. Al recalcular, ese estado entra como suelo del
SL (`ladder_floor.Guard`): el nivel protegido que se adopta es el mayor de los dos.

Solo operaciones de origen `vivo`, como el libro fijo (las reconstruidas por backtest no ocurrieron
en vivo). `paper_protection_pass` recuerda, por símbolo, cuándo empezó el diario y qué operaciones
dejó abiertas la última pasada: si después falta su fila, la instantánea falta.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from eim.data.paper_store import PaperStore
from eim.paper.ladder_floor import Floor, Guard

OPEN = ("abierta", "protegida")
HELD = "inconsistente"
STATUSES = (*OPEN, "cerrada", HELD, "descartada", "reconciliada")
EVENTS = ("alta", "escalon", "recuperacion", "cierre", "inconsistente", "reconciliada")
COLS = ("row_id", "op_id", "seq", "event", "profile", "symbol", "idea_id", "side", "entry",
        "qty", "notional", "initial_sl", "first_usd", "step_usd", "active", "max_float_usd",
        "level", "protected_usd", "stop", "stop_source", "updated_t", "costs", "status",
        "history", "close_reason", "exit_t", "exit_price", "note", "recorded_ms")
_TYPES = ("VARCHAR PRIMARY KEY, VARCHAR, INTEGER, VARCHAR, VARCHAR, VARCHAR, VARCHAR, INTEGER, "
          "DOUBLE, DOUBLE, DOUBLE, DOUBLE, DOUBLE, DOUBLE, BOOLEAN, DOUBLE, INTEGER, DOUBLE, "
          "DOUBLE, VARCHAR, BIGINT, VARCHAR, VARCHAR, VARCHAR, VARCHAR, BIGINT, DOUBLE, VARCHAR, "
          "BIGINT").split(", ")
DDL = ("CREATE TABLE IF NOT EXISTS paper_protection (" +
       ", ".join(f"{c} {t}" for c, t in zip(COLS, _TYPES, strict=True)) + ")")
DDL_PASS = ("CREATE TABLE IF NOT EXISTS paper_protection_pass (symbol VARCHAR PRIMARY KEY, "
            "first_ms BIGINT, last_ms BIGINT, open_ids VARCHAR)")
_LATEST = " QUALIFY row_number() OVER (PARTITION BY op_id ORDER BY seq DESC NULLS LAST) = 1"


def ensure(pstore: PaperStore) -> None:
    pstore.execute(DDL)
    pstore.execute(DDL_PASS)


def op_key(profile: str, symbol: str, idea_id: str) -> str:
    return f"{profile}|{symbol}|{idea_id}"


def split(op_id: str) -> tuple[str, str, str] | None:
    """(perfil, símbolo, idea) de un identificador de operación; None si no se puede leer."""
    parts = op_id.split("|", 2) if isinstance(op_id, str) else []
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 and all(parts) else None


def _dicts(rows: list[tuple]) -> list[dict]:
    return [dict(zip(COLS, r, strict=True)) for r in rows]


def latest(pstore: PaperStore, symbol: str | None = None) -> dict[str, dict]:
    """Fila vigente (la de mayor `seq`) de cada operación; por símbolo según su identificador, no
    según la columna `symbol` (una fila con el símbolo cambiado se detecta, no se pierde)."""
    sql = (f"SELECT {', '.join(COLS)} FROM paper_protection"
           + (" WHERE split_part(op_id, '|', 2) = ?" if symbol else "") + _LATEST)
    return {r["op_id"]: r for r in _dicts(pstore.execute(sql, [symbol] if symbol else []))}


def history(pstore: PaperStore, op_id: str) -> list[dict]:
    """Todas las filas de una operación, de la primera a la vigente."""
    return _dicts(pstore.execute(f"SELECT {', '.join(COLS)} FROM paper_protection "
                                 "WHERE op_id = ? ORDER BY seq", [op_id]))


def append(pstore: PaperStore, rows: list[dict]) -> int:
    """Añade filas nuevas; una clave repetida es un error (nunca se reescribe el pasado)."""
    if rows:
        ph = ", ".join("?" * len(COLS))
        pstore.executemany(f"INSERT INTO paper_protection VALUES ({ph})",
                           [tuple(r[c] for c in COLS) for r in rows])
    return len(rows)


def read_pass(pstore: PaperStore, symbol: str) -> tuple[int | None, set[str]]:
    """(cuándo empezó el diario de `symbol`, operaciones que dejó abiertas la última pasada)."""
    got = pstore.execute("SELECT first_ms, open_ids FROM paper_protection_pass WHERE symbol = ?",
                         [symbol])
    if not got:
        return None, set()
    try:
        ids = set(json.loads(got[0][1] or "[]"))
    except (TypeError, ValueError):
        ids = set()
    return int(got[0][0]), ids


def write_pass(pstore: PaperStore, symbol: str, first_ms: int, now: int,
               open_ids: set[str]) -> None:
    pstore.execute("INSERT OR REPLACE INTO paper_protection_pass VALUES (?, ?, ?, ?)",
                   [symbol, first_ms, now, json.dumps(sorted(open_ids))])


def _num(x) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x) and x > 0


def problem(row: dict) -> str:
    """Por qué una fila no sirve para reconstruir la operación ("" = válida)."""
    ids = split(row.get("op_id"))
    if ids is None:
        return "identificador de operación ilegible"
    if row.get("symbol") != ids[1]:
        return f"el símbolo guardado ({row.get('symbol')}) no cuadra con la operación ({ids[1]})"
    if (row.get("profile"), row.get("idea_id")) != (ids[0], ids[2]):
        return "el perfil o la idea guardados no cuadran con la operación"
    if not isinstance(row.get("seq"), int) or row["seq"] < 1:
        return "número de fila ausente"
    if row.get("status") not in STATUSES:
        return f"estado desconocido «{row.get('status')}»"
    try:
        hist = json.loads(row.get("history") or "")
    except (TypeError, ValueError):
        hist = None
    if not isinstance(hist, list):
        return "historial de cambios ilegible"
    if row["status"] in (*OPEN, HELD):
        if not all(_num(row.get(k)) for k in ("entry", "qty", "stop")):
            return "entrada, cantidad o stop ausentes o no válidos"
        if row.get("side") not in (1, -1):
            return "lado ausente o no válido"
        lvl = row.get("level")
        if not isinstance(lvl, int) or lvl < 0 or row.get("updated_t") is None:
            return "escalón o instante de actualización ausentes"
        if row.get("active") and (row["stop"] - row["entry"]) * row["side"] <= 0:
            return "stop protegido en la entrada o peor"
    return ""


def floor_of(row: dict) -> Floor:
    return Floor(seq=int(row["seq"]), t=int(row["updated_t"]), side=int(row["side"]),
                 fill=float(row["entry"]), qty=float(row["qty"]), stop=float(row["stop"]),
                 level=int(row["level"]), protected_usd=row.get("protected_usd"),
                 max_float_usd=row.get("max_float_usd"), source=row.get("stop_source") or "")


@dataclass
class Journal:
    """Lo leído del diario para un símbolo ANTES de recalcular la vista."""

    symbol: str
    latest: dict[str, dict] = field(default_factory=dict)
    problems: dict[str, str] = field(default_factory=dict)   # op_id → fila vigente corrupta
    prev_open: set[str] = field(default_factory=set)
    first_ms: int | None = None
    guards: dict[tuple[str, str], Guard] = field(default_factory=dict)


MISSING = "falta la instantánea de una operación que el diario dejó abierta"


def load(pstore: PaperStore, symbol: str) -> Journal:
    """Lee el diario de `symbol` y arma el suelo de cada operación (`LadderSim.guards`)."""
    j = Journal(symbol, latest(pstore, symbol))
    j.first_ms, j.prev_open = read_pass(pstore, symbol)
    for op_id, row in j.latest.items():
        ids = split(op_id)
        if ids is None:
            j.problems[op_id] = "identificador de operación ilegible"
            continue
        key = (ids[0], ids[2])
        why = problem(row)
        if why:
            j.problems[op_id] = why
        if row.get("status") == HELD:
            j.guards[key] = Guard(None if why else floor_of(row), row.get("note") or HELD)
        elif why:
            j.guards[key] = Guard(None, f"instantánea corrupta: {why}")
        elif row["status"] in OPEN:
            j.guards[key] = Guard(floor_of(row))
    for op_id in j.prev_open - set(j.latest):
        ids = split(op_id)
        if ids is not None:
            j.guards[(ids[0], ids[2])] = Guard(None, MISSING)
    return j


def overview(pstore: PaperStore, symbol: str | None = None, status: str | None = None,
             limit: int = 500) -> list[dict]:
    """Filas vigentes (más recientes primero) con el historial ya decodificado, para la API."""
    out = []
    for r in sorted(latest(pstore, symbol).values(), key=lambda r: -(r["recorded_ms"] or 0)):
        if status is not None and r["status"] != status:
            continue
        d = dict(r)
        try:
            d["history"] = json.loads(r["history"] or "[]")
            d["costs"] = json.loads(r["costs"] or "{}")
        except (TypeError, ValueError):
            d["problem"] = problem(r) or "fila ilegible"
        out.append(d)
    return out[:limit]
