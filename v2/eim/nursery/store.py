"""Persistencia del libro de la cantera en su propia base (`data/paper_cantera.duckdb`, T168).

Nunca toca `paper.duckdb` (contextos y libros de T31): de ella solo **lee** los campos que la
cantera usa, sin parsear el contexto entero. El registro de cuentas es de solo adición (una
cuenta nueva aparece con su hora de alta y no hereda operaciones); operaciones, eventos y la
serie diaria se reescriben enteras con cada recálculo, en una transacción.
"""

from __future__ import annotations

import json

from eim.data.paper_store import PaperStore
from eim.nursery.book import Book
from eim.nursery.signals import Account
from eim.nursery.summary import DAY_MS

DDL = (
    """CREATE TABLE IF NOT EXISTS nursery_accounts (account_id VARCHAR PRIMARY KEY,
       kind VARCHAR, prospect_id VARCHAR, fingerprint VARCHAR, timeframe VARCHAR,
       registered_ms BIGINT)""",
    """CREATE TABLE IF NOT EXISTS nursery_trades (account_id VARCHAR, t BIGINT, side INTEGER,
       booked BOOLEAN, status VARCHAR, reason VARCHAR, fill_t BIGINT, fill DOUBLE, exit_t BIGINT,
       exit DOUBLE, qty DOUBLE, risk_usd DOUBLE, balance_before DOUBLE, pnl_usd DOUBLE,
       r DOUBLE, cost_r DOUBLE, markout_bps DOUBLE, twin_k INTEGER, twin_long INTEGER,
       twin_r_long DOUBLE, twin_r_short DOUBLE, twin_mean_r DOUBLE, d_r DOUBLE, maker BOOLEAN,
       PRIMARY KEY (account_id, t))""",
    "CREATE TABLE IF NOT EXISTS nursery_events (t BIGINT, kind VARCHAR, payload VARCHAR)",
    """CREATE TABLE IF NOT EXISTS nursery_daily (account_id VARCHAR, day BIGINT,
       pnl_usd DOUBLE, twin_pnl_usd DOUBLE, PRIMARY KEY (account_id, day))""",
)
CTX_FIELDS = ("SELECT asof_ms, json_extract(ctx, '$.close'), json_extract(ctx, '$.atr'), "
              "json_extract(ctx, '$.agents'), json_extract(ctx, '$.nat') FROM paper_ctx "
              "WHERE symbol = ? AND timeframe = ? AND asof_ms >= ? ORDER BY asof_ms")


def _num(x) -> float | None:
    return None if x is None else float(json.loads(x)) if isinstance(x, str) else float(x)


def light_contexts(ctx_store, symbol: str, timeframe: str, start: int) -> list[dict]:
    """Solo `t`, `close`, `atr`, `agents` y `nat` de cada contexto (lectura, sin escribir)."""
    rows = ctx_store.execute(CTX_FIELDS, [symbol, timeframe, int(start)])
    return [{"t": int(t), "close": _num(c), "atr": _num(a),
             "agents": json.loads(ag) if ag else {}, "nat": json.loads(nat) if nat else None}
            for t, c, a, ag, nat in rows]


class NurseryStore:
    def __init__(self, own: PaperStore) -> None:
        self.own = own
        for q in DDL:
            own.execute(q)

    def register(self, accounts: list[Account], now_ms: int) -> dict[str, int]:
        """Alta de las cuentas nuevas (con su hora) y horas de alta de todas."""
        have = {a: int(t) for a, t in self.own.execute(
            "SELECT account_id, registered_ms FROM nursery_accounts")}
        new = [(a.id, a.kind, a.prospect.id if a.prospect else None,
                a.prospect.fingerprint if a.prospect else None, a.timeframe, now_ms)
               for a in accounts if a.id not in have]
        self.own.executemany("INSERT INTO nursery_accounts VALUES (?,?,?,?,?,?)", new)
        return {**have, **{r[0]: now_ms for r in new}}

    def save(self, book: Book) -> None:
        trades, daily = [], {}
        for e in book.entries:
            tr, tw = e.trade, e.twins
            trades.append((e.account, e.t, e.side, e.booked, tr.status, tr.reason, tr.fill_t,
                           tr.fill, tr.exit_t, tr.exit, e.qty, e.risk_usd, e.balance_before,
                           e.pnl_usd, tr.r, tr.cost_r, tr.markout_bps,
                           tw.k if tw else None, tw.n_long if tw else None,
                           tw.r_long if tw else None, tw.r_short if tw else None,
                           tw.mean_r if tw else None, e.d_r, e.order.maker))
            if e.booked and tr.status == "CERRADA":
                key = (e.account, int(tr.exit_t) // DAY_MS)
                acc = daily.setdefault(key, [0.0, 0.0])
                acc[0] += e.pnl_usd
                acc[1] += e.twin_pnl_usd
        events = [(int(ev.get("t") or 0), ev["kind"], json.dumps(ev, ensure_ascii=False))
                  for ev in book.events]
        con, lock = self.own.connection
        with lock:
            con.execute("BEGIN TRANSACTION")
            try:
                for tbl in ("nursery_trades", "nursery_events", "nursery_daily"):
                    con.execute(f"DELETE FROM {tbl}")
                if trades:
                    con.executemany("INSERT INTO nursery_trades VALUES (" +
                                    ",".join("?" * 24) + ")", trades)
                if events:
                    con.executemany("INSERT INTO nursery_events VALUES (?,?,?)", events)
                if daily:
                    con.executemany("INSERT INTO nursery_daily VALUES (?,?,?,?)",
                                    [(a, d, v[0], v[1]) for (a, d), v in daily.items()])
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
