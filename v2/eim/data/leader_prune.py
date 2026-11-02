"""Poda de los líderes rechazados (T128, I/O): 7 días de detalle y lo anterior, archivado.

Por cada líder `rejected` y moneda: pliega lo posterior al corte anterior hasta el último
instante ≤ ahora − `keep_ms` en que la posición quedó plana (`trip_archive.advance`), guarda
eso en `leader_archive*` y borra en la MISMA transacción sus ejecuciones (`leader_fills`, t ≤
corte) y las cotizaciones del seguidor de esas ejecuciones (`leader_follow`). Lo lee y lo borra
en una sola instantánea: lo que la captura escribe mientras tanto no se toca. Si la
transacción choca con otra escritura, se deshace entera y se reintenta en la próxima poda.

Al final de cada líder se borra la procedencia de la unión T61 (`share_origin`, si existe) de
lo que ya no está: sin eso la tabla más grande de la base (5,2 M claves de texto el
2026-11-02) guardaría huérfanas para siempre. Una pasada por líder y no por lote: cada pasada
recorre la tabla entera (lote a lote, la primera poda tardaba 314 s en vez de 92).
Aprobados y `watch` no se tocan; tampoco funding, posiciones, reconciliaciones ni huecos. Las
filas borradas dejan bloques libres que DuckDB reutiliza (la base deja de crecer); el archivo
encoge con el compactado al arrancar (`duck_compact.py`). Lotes de `STEP_ROWS` ejecuciones
por transacción: la primera poda (2,6 M filas de un solo líder) no frena la captura.

La corre el servicio de líderes una vez al día (`LeaderService`), el vigilante antes de lanzar
`run` y la CLI `python -m eim.leaders prune` con el servicio apagado.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eim.copytrading.params import ScoreParams
from eim.copytrading.trip_archive import advance
from eim.data import leader_archive as archive
from eim.data.leader_fold_io import MAX_T, NO_CUT, QUOTE_FINAL_MS, _symbol_rows

DAY_MS = 86_400_000
KEEP_MS = 7 * DAY_MS
STEP_ROWS = 200_000
STATUSES = ("rejected",)
_OLD = "FROM leader_fills WHERE leader_id = ? AND symbol = ? AND t <= ?"
_ORPHANS = (  # clave = `share_merge._key_str` de (leader_id, tid, oid)
    "DELETE FROM share_origin WHERE tbl = '{t}' AND starts_with(key, ?) AND key NOT IN (SELECT "
    "concat_ws('|', CAST(leader_id AS VARCHAR), CAST(tid AS VARCHAR), CAST(oid AS VARCHAR)) "
    "FROM {t} WHERE leader_id = ?)")


@dataclass
class Pruned:
    fills: int = 0
    quotes: int = 0
    trips: int = 0
    origins: int = 0
    symbols: set[str] = field(default_factory=set)


def _drop(cur, lid: str, sym: str, cut: int, out: Pruned) -> None:
    """Borra el detalle de la moneda hasta `cut` (también lo que haya vuelto por T61)."""
    args = [lid, sym, cut]
    if not cur.execute(f"SELECT count(*) {_OLD}", args).fetchone()[0]:
        return
    out.quotes += cur.execute("DELETE FROM leader_follow WHERE leader_id = ? AND (tid, oid) IN "
                              f"(SELECT tid, oid {_OLD})", [lid, *args]).fetchone()[0]
    out.fills += cur.execute(f"DELETE {_OLD}", args).fetchone()[0]
    out.symbols.add(sym)


def _step(cur, lid: str, sym: str, base, limit: int, final: int, p: ScoreParams, now: int,
          max_rows: int, out: Pruned):
    """Un lote de una moneda en una transacción. Devuelve la base nueva (None: nada más)."""
    cur.execute("BEGIN TRANSACTION")
    try:
        after = base.cut_t if base is not None else NO_CUT
        new = advance(base, sym, _symbol_rows(cur, lid, MAX_T, sym, after, limit), final, p,
                      max_rows)
        cut = new.cut_t if new is not None else after
        if new is not None:
            out.trips += archive.save(cur, lid, base, new, p, now)
        if cut != NO_CUT:
            _drop(cur, lid, sym, cut, out)
        cur.execute("COMMIT")
    except BaseException:
        cur.execute("ROLLBACK")
        raise
    return new


def prune_leader(store, lid: str, now: int, p: ScoreParams | None = None,
                 keep_ms: int = KEEP_MS, max_rows: int = STEP_ROWS) -> Pruned:
    p = p or ScoreParams()
    limit, final = now - keep_ms, now - QUOTE_FINAL_MS
    out = Pruned()
    con, lock = store.connection
    with lock:
        cur = con.cursor()
    try:
        bases = archive.load(cur, lid, p)
        syms = [r[0] for r in cur.execute(
            "SELECT DISTINCT symbol FROM leader_fills WHERE leader_id = ? AND t <= ? ORDER BY 1",
            [lid, limit]).fetchall()]
        for sym in syms:
            base = bases.get(sym)
            while True:
                new = _step(cur, lid, sym, base, limit, final, p, now, max_rows, out)
                if new is None:
                    break
                base = new
        if out.fills and cur.execute(
                "SELECT count(*) FROM duckdb_tables() WHERE database_name = current_database() "
                "AND table_name = 'share_origin'").fetchone()[0]:
            for t in ("leader_fills", "leader_follow"):
                out.origins += cur.execute(_ORPHANS.format(t=t), [lid + "|", lid]).fetchone()[0]
    finally:
        cur.close()
    return out


def prune(store, now: int, p: ScoreParams | None = None, keep_ms: int = KEEP_MS,
          max_rows: int = STEP_ROWS) -> dict[str, Pruned]:
    """Poda a todos los rechazados; devuelve lo hecho por líder (solo los que cambiaron)."""
    out = {}
    for ld in store.leaders(STATUSES):
        got = prune_leader(store, ld.id, now, p, keep_ms, max_rows)
        if got.fills or got.trips:
            out[ld.id] = got
    return out
