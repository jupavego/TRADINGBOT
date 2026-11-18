"""Retención de lo que la poda de T128 no toca (T178, I/O): reconciliaciones y fotos.

La poda de T128 (`leader_prune.py`) pliega el detalle de los líderes rechazados, pero deja
intactas las reconciliaciones y las fotos de posiciones, que crecen para siempre. Aquí se
conserva lo que algún lector necesita y se borra lo demás, con la misma regla que T128: se lee
y se borra en la MISMA transacción, en lotes acotados, sin frenar la captura.

Reconciliaciones (`leader_recon`). Pasados `keep_ms`:
  * se quedan TODAS las que no cuadran (`match = false`) o resincronizaron;
  * de las correctas, una por líder cada `RECON_GRID_MS` (por debajo del `recon_gap_ms` de la
    copia simulada, 5 min, para no inventar huecos de flujo al repetir una corrida);
  * de las borradas queda el resumen por día y líder en `leader_recon_daily` (comprobadas,
    saltadas, desfase de reloj medio y máximo), que es lo que lee `leader_report.py`.

Fotos de posiciones (`leader_positions`). Pasados `keep_ms` se queda la foto de cada cambio de
forma (lo que compara `_shape`: moneda, lado, tamaño, entrada, apalancamiento y modo de margen),
una cada `PHOTO_KEEP_MS` y la última de cada tanda. Para que el tiempo capturado
(`observed_ms`, el que mide T49) no cambie al borrar, antes de borrar se suma el tiempo que
cubrían las fotos originales y se guarda en `leader_photo_cover`; `leader_eval.context` lee de
ahí lo anterior al corte y solo cuenta las fotos que quedan a partir de él.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

DAY_MS = 86_400_000
KEEP_MS = 7 * DAY_MS
PHOTO_STEP_MS = 15 * 60_000      # salto entre fotos que aún cuenta como tiempo capturado
PHOTO_KEEP_MS = 3_600_000        # sin cambios, una foto por hora
RECON_GRID_MS = 120_000          # confirmación de flujo cada 2 min (recon_gap_ms = 5 min)
STEP_ROWS = 5_000                # fotas por transacción (cada una pesa ~5 KB de JSON)
_SHAPE = ("symbol", "side", "size", "entry", "leverage", "margin_mode")


@dataclass
class Retained:
    recon_dropped: int = 0
    recon_days: int = 0
    photos_dropped: int = 0
    photos_kept: int = 0
    leaders: int = 0

    def to_json(self) -> dict:
        return {"recon_borradas": self.recon_dropped, "recon_resumidas_dias": self.recon_days,
                "fotos_borradas": self.photos_dropped, "fotos_conservadas": self.photos_kept,
                "lideres": self.leaders}

    def __bool__(self) -> bool:
        return bool(self.recon_dropped or self.photos_dropped)


def shape(raw: str | None) -> str:
    """La forma de una foto: lo que define la posición, sin PnL ni margen (cambian con el
    precio). Mismo criterio que `LeaderStore._shape`, sobre el JSON ya guardado y como texto
    (así se guarda en `leader_photo_cover` para enlazar una tanda con la siguiente)."""
    try:
        ps = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return f"?{raw}"
    return json.dumps(sorted([p.get(k) for k in _SHAPE] for p in ps), separators=(",", ":"))


# --- reconciliaciones -------------------------------------------------------------------------

_DROP = """
SELECT rowid FROM leader_recon
WHERE observed_at >= ? AND observed_at < ? AND match AND NOT coalesce(resynced, false)
QUALIFY row_number() OVER (PARTITION BY leader_id, machine, observed_at // ?
                           ORDER BY observed_at) > 1"""
_SUMMARY = f"""
INSERT INTO leader_recon_daily
SELECT leader_id, (observed_at // {DAY_MS}) * {DAY_MS}, coalesce(machine, ''), count(*),
       sum(size_ok::INT),
       sum(match::INT), sum(resynced::INT), sum(checked), sum(skipped),
       sum((size_ok AND coalesce(retries, 0) > 0)::INT), sum(coalesce(clock_offset_ms, 0)),
       count(clock_offset_ms), max(clock_offset_ms), min(observed_at), max(observed_at)
FROM leader_recon WHERE rowid IN ({_DROP})
GROUP BY 1, 2, 3
ON CONFLICT (leader_id, day, machine) DO UPDATE SET
    checks = leader_recon_daily.checks + excluded.checks,
    size_ok = leader_recon_daily.size_ok + excluded.size_ok,
    matched = leader_recon_daily.matched + excluded.matched,
    resynced = leader_recon_daily.resynced + excluded.resynced,
    coins_checked = leader_recon_daily.coins_checked + excluded.coins_checked,
    coins_skipped = leader_recon_daily.coins_skipped + excluded.coins_skipped,
    after_retry = leader_recon_daily.after_retry + excluded.after_retry,
    offset_sum = leader_recon_daily.offset_sum + excluded.offset_sum,
    offset_n = leader_recon_daily.offset_n + excluded.offset_n,
    offset_max = greatest(leader_recon_daily.offset_max, excluded.offset_max),
    first_at = least(leader_recon_daily.first_at, excluded.first_at),
    last_at = greatest(leader_recon_daily.last_at, excluded.last_at)"""


def thin_recon(store, now: int, keep_ms: int = KEEP_MS, grid_ms: int = RECON_GRID_MS,
               out: Retained | None = None) -> Retained:
    """Resume y borra, día a día (una transacción por día), las que cuadran y sobran."""
    out = Retained() if out is None else out
    cut = now - keep_ms
    con, lock = store.connection
    with lock:
        cur = con.cursor()
    try:
        days = [r[0] for r in cur.execute(
            f"SELECT DISTINCT (observed_at // {DAY_MS}) * {DAY_MS} d FROM leader_recon "
            "WHERE observed_at < ? AND match AND NOT coalesce(resynced, false) ORDER BY 1",
            [cut]).fetchall()]
        for day in days:
            hi = min(day + DAY_MS, cut)
            args = [day, hi, grid_ms]
            cur.execute("BEGIN TRANSACTION")
            try:
                cur.execute(_SUMMARY, args)
                n = cur.execute(f"DELETE FROM leader_recon WHERE rowid IN ({_DROP})",
                                args).fetchone()[0]
                cur.execute("COMMIT")
            except BaseException:
                cur.execute("ROLLBACK")
                raise
            if n:
                out.recon_dropped += n
                out.recon_days += 1
    finally:
        cur.close()
    return out


# --- fotos de posiciones ----------------------------------------------------------------------

def _cover(cur, lid: str) -> tuple[int, int, int | None, str | None]:
    row = cur.execute("SELECT cut_t, covered_ms, first_at, last_shape FROM leader_photo_cover "
                      "WHERE leader_id = ?", [lid]).fetchone()
    return row if row else (0, 0, None, None)


def _photo_batch(cur, lid: str, since: int, cut: int, limit: int) -> list[tuple]:
    return cur.execute(
        "SELECT rowid, observed_at, positions FROM leader_positions WHERE leader_id = ? "
        "AND observed_at > ? AND observed_at <= ? ORDER BY observed_at LIMIT ?",
        [lid, since, cut, limit]).fetchall()


def _decide(rows: list[tuple], prev_shape: str | None, last_kept: int,
            keep_ms: int) -> tuple[list[int], int, str | None, int]:
    """Qué `rowid` sobran. Se quedan las que cambian de forma y una cada `keep_ms`; la decisión
    no depende de dónde caiga el corte de la tanda (`leader_photo_cover` enlaza las tandas)."""
    drop, kept = [], 0
    for rid, obs, raw in rows:
        sh = shape(raw)
        if sh != prev_shape or obs - last_kept >= keep_ms:
            kept += 1
            last_kept = obs
        else:
            drop.append(rid)
        prev_shape = sh
    return drop, kept, prev_shape, last_kept


def thin_photos(store, now: int, keep_ms: int = KEEP_MS, photo_keep_ms: int = PHOTO_KEEP_MS,
                step_ms: int = PHOTO_STEP_MS, max_rows: int = STEP_ROWS,
                out: Retained | None = None) -> Retained:
    """Adelanta el corte de cada líder en tandas; cada tanda, una transacción."""
    out = Retained() if out is None else out
    cut = now - keep_ms
    con, lock = store.connection
    with lock:
        cur = con.cursor()
    try:
        lids = [r[0] for r in cur.execute(
            "SELECT DISTINCT leader_id FROM leader_positions WHERE observed_at <= ? ORDER BY 1",
            [cut]).fetchall()]
        for lid in lids:
            if _thin_one(cur, lid, cut, photo_keep_ms, step_ms, max_rows, out):
                out.leaders += 1
    finally:
        cur.close()
    return out


def _thin_one(cur, lid: str, cut: int, photo_keep_ms: int, step_ms: int, max_rows: int,
              out: Retained) -> bool:
    cut_t, covered, first_at, prev_shape = _cover(cur, lid)
    if cut <= cut_t:
        return False
    last_kept, touched = cut_t, False
    while True:
        cur.execute("BEGIN TRANSACTION")      # se lee y se borra en la misma transacción (T128)
        try:
            rows = _photo_batch(cur, lid, cut_t, cut, max_rows)
            if not rows:
                cur.execute("ROLLBACK")
                break
            add = sum(min(b[1] - a[1], step_ms) for a, b in zip(rows, rows[1:], strict=False))
            if cut_t:
                add += min(rows[0][1] - cut_t, step_ms)
            drop, kept, prev_shape, last_kept = _decide(rows, prev_shape, last_kept,
                                                        photo_keep_ms)
            first = first_at if first_at is not None else rows[0][1]
            if drop:
                cur.execute("DELETE FROM leader_positions WHERE rowid IN "
                            f"({', '.join(['?'] * len(drop))})", drop)
            cur.execute(
                "INSERT INTO leader_photo_cover VALUES (?,?,?,?,?,?,?) ON CONFLICT (leader_id) "
                "DO UPDATE SET cut_t = excluded.cut_t, covered_ms = excluded.covered_ms, "
                "first_at = excluded.first_at, kept = leader_photo_cover.kept + excluded.kept, "
                "dropped = leader_photo_cover.dropped + excluded.dropped, "
                "last_shape = excluded.last_shape",
                [lid, rows[-1][1], covered + add, first, kept, len(drop), prev_shape])
            cur.execute("COMMIT")
        except BaseException:
            cur.execute("ROLLBACK")
            raise
        cut_t, covered, first_at, touched = rows[-1][1], covered + add, first, True
        out.photos_dropped += len(drop)
        out.photos_kept += kept
        if len(rows) < max_rows:
            break
    return touched


def retain(store, now: int, keep_ms: int = KEEP_MS, **kw) -> Retained:
    """Las dos retenciones de T178; la corre el servicio tras la poda diaria de T128."""
    out = Retained()
    thin_recon(store, now, keep_ms, out=out)
    thin_photos(store, now, keep_ms, out=out, **kw)
    return out
