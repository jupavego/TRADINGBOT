"""Tablas del archivo de líderes (T128) dentro de `data/leaders.duckdb`.

- `leader_archive`: por (líder, moneda), hasta dónde se archivó (`cut_t`), la posición en ese
  instante, las cuentas (ejecuciones, tomadoras, histograma de latencias en JSON) y con qué
  parámetros y versión de formato se plegó.
- `leader_archive_trips`: cada viaje archivado con todos sus campos y su seguidor plegado
  (`f_*`; los deslizamientos por pata, en una lista de DOUBLE). Sin pickle: columnas y JSON.
  El viaje que seguía abierto en el corte (`SymbolBase.open`) va con `seq = -1` y se reescribe
  en cada poda; no cuenta en `n_trips`. Un archivo de antes no tiene esa fila: sigue valiendo.

Las escribe la poda (`leader_prune.py`) en la misma transacción que borra el detalle; las lee
la evaluación (`leader_fold_io.py`) con el mismo cursor que las ejecuciones. No viajan en la
experiencia compartida (T61): cada equipo archiva lo suyo.
"""

from __future__ import annotations

import json
import logging
from array import array
from collections import defaultdict

from eim.copytrading.copyability import TripFollow
from eim.copytrading.params import ScoreParams
from eim.copytrading.trip_archive import params_of
from eim.copytrading.trip_fold import FoldTrip, SymbolBase

VERSION = 1
CHUNK = 5_000
OPEN_SEQ = -1  # el viaje abierto en el corte
ARCHIVE_DDL = """
CREATE TABLE IF NOT EXISTS leader_archive (
    leader_id VARCHAR, symbol VARCHAR, cut_t BIGINT, prev DOUBLE, n BIGINT, taker_x BIGINT,
    taker_n BIGINT, latency VARCHAR, n_trips INTEGER, params VARCHAR, version INTEGER,
    pruned_at BIGINT, PRIMARY KEY (leader_id, symbol));
CREATE TABLE IF NOT EXISTS leader_archive_trips (
    leader_id VARCHAR, symbol VARCHAR, seq INTEGER, side VARCHAR, t_open BIGINT, t_close BIGINT,
    complete BOOLEAN, before_history BOOLEAN, pnl DOUBLE, fees DOUBLE, size_max DOUBLE,
    notional_max DOUBLE, first_size DOUBLE, avg_downs INTEGER, leverage_max DOUBLE,
    liquidated BOOLEAN, in_qty DOUBLE, in_cost DOUBLE, out_qty DOUBLE, out_cost DOUBLE,
    pos DOUBLE, n_legs BIGINT, n_taker BIGINT, f_ok BOOLEAN, f_stale BIGINT, f_quoted BIGINT,
    f_src VARCHAR, f_slips DOUBLE[], f_cash DOUBLE, f_fees DOUBLE,
    PRIMARY KEY (leader_id, symbol, seq));
"""
# Campos de `Trip` que se guardan (todos menos moneda, patas, funding, que se reparte de nuevo
# con `leader_funding`, y el seguidor, en `f_*`); columna = nombre sin el guion bajo.
TRIP_FIELDS = ("side", "t_open", "t_close", "complete", "before_history", "pnl", "fees",
               "size_max", "notional_max", "first_size", "avg_downs", "leverage_max",
               "liquidated", "_in_qty", "_in_cost", "_out_qty", "_out_cost", "_pos", "_n_legs",
               "_n_taker")
_TRIP_COLS = ", ".join(k.lstrip("_") for k in TRIP_FIELDS)
_F_COLS = "f_ok, f_stale, f_quoted, f_src, f_slips, f_cash, f_fees"
_ALL_COLS = f"leader_id, symbol, seq, {_TRIP_COLS}, {_F_COLS}"

log = logging.getLogger(__name__)


def generation(cur, lid: str) -> tuple[int, int]:
    """(monedas, ejecuciones) archivadas: cambia con cada poda del líder."""
    n, rows = cur.execute("SELECT count(*), coalesce(sum(n), 0) FROM leader_archive "
                          "WHERE leader_id = ?", [lid]).fetchone()
    return int(n), int(rows)


def floor(store, lid: str) -> int | None:
    """Último corte del líder: todo lo posterior conserva su detalle en todas las monedas."""
    return store.query("SELECT max(cut_t) FROM leader_archive WHERE leader_id = ?", [lid])[0][0]


def _trip(symbol: str, r: tuple) -> FoldTrip:
    k = len(TRIP_FIELDS)
    tr = FoldTrip(symbol, **dict(zip(TRIP_FIELDS, r[:k], strict=True)))
    ok, stale, quoted, src, slips, cash, fees = r[k:]
    tr.follow = TripFollow(ok, stale, quoted, json.loads(src), array("d", slips), cash, fees)
    return tr


def load(cur, lid: str, p: ScoreParams) -> dict[str, SymbolBase]:
    """Lo archivado del líder por moneda (vacío si nada). Lo plegado con otros parámetros se usa
    igual (el detalle ya no existe) y se avisa en el registro."""
    heads = cur.execute("SELECT symbol, cut_t, prev, n, taker_x, taker_n, latency, n_trips, "
                        "params, version FROM leader_archive WHERE leader_id = ? ORDER BY symbol",
                        [lid]).fetchall()
    if not heads:
        return {}
    trips: dict[str, list[FoldTrip]] = defaultdict(list)
    opened: dict[str, FoldTrip] = {}
    cur.execute(f"SELECT symbol, seq, {_TRIP_COLS}, {_F_COLS} FROM leader_archive_trips WHERE "
                "leader_id = ? ORDER BY symbol, seq", [lid])
    while batch := cur.fetchmany(CHUNK):
        for r in batch:
            if r[1] == OPEN_SEQ:
                opened[r[0]] = _trip(r[0], r[2:])
            else:
                trips[r[0]].append(_trip(r[0], r[2:]))
    out, want = {}, params_of(p)
    for sym, cut_t, prev, n, tx, tn, lat, n_trips, params, version in heads:
        if version != VERSION:
            raise ValueError(f"archivo de {lid}/{sym}: versión {version} desconocida")
        if len(trips[sym]) != n_trips:
            raise ValueError(f"archivo de {lid}/{sym}: {len(trips[sym])} viajes de {n_trips}")
        if json.loads(params) != want:
            log.warning("archivo de %s/%s plegado con otros parámetros: %s", lid, sym, params)
        out[sym] = SymbolBase(sym, cut_t, prev, trips[sym], n, (tx, tn),
                              {ch: {int(ms): k for ms, k in h}
                               for ch, h in json.loads(lat).items()}, opened.get(sym))
    return out


def _row(lid: str, seq: int, tr: FoldTrip) -> tuple:
    f = tr.follow
    return (lid, tr.symbol, seq, *(getattr(tr, k) for k in TRIP_FIELDS), f.ok, f.stale,
            f.quoted, json.dumps(f.src), list(f.slips), f.cash, f.fees)


def save(cur, lid: str, old: SymbolBase | None, new: SymbolBase, p: ScoreParams, now: int,
         chunk: int = 200) -> int:
    """Escribe la base nueva (solo los viajes que no estaban en `old`) dentro de la transacción
    abierta en `cur`. Devuelve los viajes cerrados añadidos (el abierto se reescribe aparte)."""
    lat = {ch: sorted(h.items()) for ch, h in sorted(new.latency.items())}
    cur.execute("INSERT OR REPLACE INTO leader_archive VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [lid, new.symbol, new.cut_t, new.prev, new.n, new.taker[0], new.taker[1],
                 json.dumps(lat), len(new.trips), json.dumps(params_of(p)), VERSION, now])
    start = len(old.trips) if old is not None else 0
    rows = [_row(lid, start + i, tr) for i, tr in enumerate(new.trips[start:])]
    added = len(rows)
    cur.execute("DELETE FROM leader_archive_trips WHERE leader_id = ? AND symbol = ? AND seq = ?",
                [lid, new.symbol, OPEN_SEQ])
    if new.open is not None:
        rows.append(_row(lid, OPEN_SEQ, new.open))
    one = "(" + ", ".join("?" * len(rows[0])) + ")" if rows else ""
    for k in range(0, len(rows), chunk):
        part = rows[k:k + chunk]
        cur.execute(f"INSERT INTO leader_archive_trips ({_ALL_COLS}) VALUES "
                    + ", ".join([one] * len(part)), [x for r in part for x in r])
    return added
