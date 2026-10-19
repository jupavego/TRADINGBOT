"""Registro inmutable de sugerencias publicadas (T51), en `data/paper.duckdb`.

- `sug_published`: cada oportunidad la primera vez que el panel la publica (id = id de la idea;
  una repetición no la modifica): precios, `estrategia@marco@versión`, veredicto y evidencia de
  ese momento, y la hora. Nunca se actualiza ni se marca como ejecutada.
- `sug_gaps`: intervalos observados sin sugerencia (estado y motivo), para medir cuánto tiempo
  no hubo ninguna.
- `sug_review`: versiones «en revisión» por degradación (el publicador las excluye).
Comparte conexión y candado con `PaperStore` (un solo proceso escritor).
"""

from __future__ import annotations

import json

from eim.data.paper_store import PaperStore

_DDL = (
    """CREATE TABLE IF NOT EXISTS sug_published (
        id VARCHAR PRIMARY KEY, symbol VARCHAR, published_ms BIGINT, criteria VARCHAR,
        verdicts_asof BIGINT, vid VARCHAR, sid VARCHAR, strategy VARCHAR, timeframe VARCHAR,
        n INTEGER, fingerprint VARCHAR, side INTEGER, kind VARCHAR, entry DOUBLE, sl DOUBLE,
        tp DOUBLE, fill_ms BIGINT, hold_ms BIGINT, idea_t BIGINT, price DOUBLE, reason VARCHAR,
        evidence VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS sug_gaps (
        symbol VARCHAR, started_ms BIGINT, last_ms BIGINT, status VARCHAR, message VARCHAR,
        PRIMARY KEY (symbol, started_ms))""",
    """CREATE TABLE IF NOT EXISTS sug_review (
        symbol VARCHAR, vid VARCHAR, since_ms BIGINT, verdict_asof BIGINT, mean_r DOUBLE,
        ci_low DOUBLE, n INTEGER, released_ms BIGINT, PRIMARY KEY (symbol, vid, since_ms))""",
)
PUB_COLS = ("id, symbol, published_ms, criteria, verdicts_asof, vid, sid, strategy, timeframe, "
            "n, fingerprint, side, kind, entry, sl, tp, fill_ms, hold_ms, idea_t, price, "
            "reason, evidence")


class SuggestionStore:
    def __init__(self, pstore: PaperStore) -> None:
        self.ps = pstore
        for ddl in _DDL:
            self.ps.execute(ddl)

    # --- publicaciones ----------------------------------------------------------------
    def publish(self, row: dict) -> bool:
        """Inserta la publicación si su id no existe (idempotente); True si era nueva."""
        if self.ps.execute("SELECT 1 FROM sug_published WHERE id = ?", [row["id"]]):
            return False
        vals = [json.dumps(row[c], ensure_ascii=False) if c == "evidence" else row[c]
                for c in (x.strip() for x in PUB_COLS.split(","))]
        self.ps.execute(f"INSERT INTO sug_published ({PUB_COLS}) VALUES ({','.join('?' * 22)})",
                        vals)
        return True

    def published(self, symbol: str) -> list[dict]:
        """Publicaciones del símbolo, de la más antigua a la más reciente."""
        cols = [c.strip() for c in PUB_COLS.split(",")]
        rows = self.ps.execute(f"SELECT {PUB_COLS} FROM sug_published WHERE symbol = ? "
                               "ORDER BY published_ms, id", [symbol])
        out = [dict(zip(cols, r, strict=True)) for r in rows]
        for d in out:
            d["evidence"] = json.loads(d["evidence"])
        return out

    # --- intervalos sin sugerencia ----------------------------------------------------
    def gap(self, symbol: str, now: int, status: str, message: str, join_ms: int) -> None:
        """Extiende el intervalo abierto si tiene el mismo estado y se observó hace ≤ `join_ms`;
        si no, abre uno nuevo (el tiempo sin observar no cuenta como tiempo sin sugerencia)."""
        last = self.ps.execute("SELECT started_ms, last_ms, status FROM sug_gaps WHERE symbol = ? "
                               "ORDER BY started_ms DESC LIMIT 1", [symbol])
        if last and last[0][2] == status and now - last[0][1] <= join_ms:
            self.ps.execute("UPDATE sug_gaps SET last_ms = ?, message = ? WHERE symbol = ? AND "
                            "started_ms = ?", [now, message, symbol, last[0][0]])
        else:
            self.ps.execute("INSERT OR REPLACE INTO sug_gaps VALUES (?,?,?,?,?)",
                            [symbol, now, now, status, message])

    def gaps(self, symbol: str) -> list[dict]:
        rows = self.ps.execute("SELECT started_ms, last_ms, status, message FROM sug_gaps WHERE "
                               "symbol = ? ORDER BY started_ms", [symbol])
        return [{"from": int(a), "to": int(b), "status": s, "message": m} for a, b, s, m in rows]

    # --- revisión ---------------------------------------------------------------------
    def reviews(self, symbol: str, open_only: bool = False) -> list[dict]:
        rows = self.ps.execute(
            "SELECT vid, since_ms, verdict_asof, mean_r, ci_low, n, released_ms FROM sug_review "
            "WHERE symbol = ?" + (" AND released_ms IS NULL" if open_only else "")
            + " ORDER BY since_ms", [symbol])
        return [{"vid": v, "since": int(s), "verdict_asof": a, "mean_r": m, "ci_low": c,
                 "n": int(n), "released": r} for v, s, a, m, c, n, r in rows]

    def flag(self, symbol: str, vid: str, now: int, verdict_asof: int | None, mean_r: float,
             ci_low: float, n: int) -> None:
        self.ps.execute("INSERT INTO sug_review VALUES (?,?,?,?,?,?,?,NULL)",
                        [symbol, vid, now, verdict_asof, mean_r, ci_low, n])

    def release(self, symbol: str, vid: str, now: int) -> None:
        self.ps.execute("UPDATE sug_review SET released_ms = ? WHERE symbol = ? AND vid = ? AND "
                        "released_ms IS NULL", [now, symbol, vid])
