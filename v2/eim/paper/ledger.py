"""Libro de registro fijo del bróker simulado: lo que ocurrió en vivo, escrito una sola vez.

El Historial de `View` se RECALCULA en cada consulta con las reglas y costos vigentes: cambiar un
parámetro reescribe el pasado (ayer→hoy, 157 de 167 operaciones cambiaron de PnL al calibrar el
deslizamiento). Este libro es de solo adición: cuando una operación de origen `vivo` (decidida en
tiempo real) se cierra, se guarda con sus precios, costos y versiones de reglas y de mecánica y no
se vuelve a tocar (`INSERT OR IGNORE`). Dos alcances: `perfil` (la operación del libro de un perfil,
con su tamaño y PnL en USDT) y `sombra` (la idea evaluada sola, en R, para el aprendizaje).
Las reconstruidas por backtest (`origin = backtest`) no entran: no ocurrieron en vivo.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence

from eim.data.paper_store import PaperStore
from eim.paper.book import ProfileState
from eim.paper.engine import Outcome
from eim.paper.params import ExecParams
from eim.paper.versioning import exec_fingerprint

RETRO_MS = 2 * 3_600_000    # registrada > 2 h después del cierre = «retro» (al estrenar el libro)
COLS = ("ledger_id", "scope", "profile", "symbol", "idea_id", "strategy", "sid", "timeframe",
        "family", "side", "kind", "opened_t", "fill_t", "exit_t", "fill", "exit_price", "sl", "tp",
        "reason", "pnl_usdt", "r", "net_frac", "qty", "notional", "leverage", "fees", "slip",
        "funding", "funding_assumed", "weight", "floor_trade", "origin", "regime", "rules_version",
        "mech_version", "cost_params", "recorded_ms", "retro", "payload")
_TYPES = ("VARCHAR PRIMARY KEY, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, "
          "VARCHAR, INTEGER, VARCHAR, BIGINT, BIGINT, BIGINT, DOUBLE, DOUBLE, DOUBLE, DOUBLE, "
          "VARCHAR, DOUBLE, DOUBLE, DOUBLE, DOUBLE, DOUBLE, DOUBLE, DOUBLE, DOUBLE, DOUBLE, "
          "BOOLEAN, DOUBLE, BOOLEAN, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, BIGINT, "
          "BOOLEAN, VARCHAR").split(", ")
DDL = ("CREATE TABLE IF NOT EXISTS paper_ledger (" +
       ", ".join(f"{c} {t}" for c, t in zip(COLS, _TYPES, strict=True)) + ")")


def ensure(pstore: PaperStore) -> None:
    pstore.execute(DDL)


def _mech(ep: ExecParams, tf: str) -> tuple[str, str]:
    """(huella corta de la mecánica del marco, parámetros de costos en JSON)."""
    fp = exec_fingerprint(ep, tf)
    blob = json.dumps(fp, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:12], json.dumps(fp["costs"], sort_keys=True)


def _row(scope: str, profile: str, symbol: str, d: dict, ep: ExecParams, now: int,
         extra: dict) -> tuple:
    mech, costs = _mech(ep, d["timeframe"])
    lid = f"{scope}|{profile}|{symbol}|{d['id']}"
    exit_t = int(d["exit_t"])
    vals = {
        "ledger_id": lid, "scope": scope, "profile": profile, "symbol": symbol,
        "idea_id": d["id"], "strategy": d["strategy"], "sid": d["sid"],
        "timeframe": d["timeframe"], "family": d["family"], "side": int(d["side"]),
        "kind": d["kind"], "opened_t": int(d["t"]), "fill_t": d.get("fill_t"), "exit_t": exit_t,
        "fill": d.get("fill"), "exit_price": d.get("exit"), "sl": d.get("sl"), "tp": d.get("tp"),
        "reason": d.get("reason"), "pnl_usdt": extra.get("pnl"), "r": d.get("r"),
        "net_frac": extra.get("net"), "qty": extra.get("qty"), "notional": extra.get("notional"),
        "leverage": extra.get("leverage"), "fees": d.get("fees"), "slip": d.get("slip"),
        "funding": d.get("funding"), "funding_assumed": d.get("funding_assumed"),
        "weight": extra.get("weight"), "floor_trade": extra.get("floor"), "origin": d["origin"],
        "regime": d.get("regime"), "rules_version": d.get("version"), "mech_version": mech,
        "cost_params": costs, "recorded_ms": now, "retro": now - exit_t > RETRO_MS,
        "payload": json.dumps(d, default=str, separators=(",", ":")),
    }
    return tuple(vals[c] for c in COLS)


def rows_from_view(symbol: str, outcomes: Iterable[Outcome], books: dict[str, ProfileState],
                   ep: ExecParams, now: int) -> list[tuple]:
    """Filas de las operaciones CERRADAS de origen `vivo`: sombra (cada idea) y por perfil."""
    out: list[tuple] = []
    outcomes = list(outcomes)
    ver = {o.idea.id: o.idea.version for o in outcomes}
    for o in outcomes:
        if o.idea.origin == "vivo" and o.status == "CERRADA" and o.exit_t:
            d = o.to_json()
            out.append(_row("sombra", "", symbol, d, ep, now, {"net": o.net}))
    for pid, st in books.items():
        for t in st.trades:
            if t.get("origin") == "vivo":
                d = {**t, "version": ver.get(t["id"])}
                out.append(_row("perfil", pid, symbol, d, ep, now,
                                {"pnl": t["pnl"], "qty": t["qty"], "notional": t["notional"],
                                 "leverage": t["leverage"], "weight": t.get("weight"),
                                 "floor": t.get("floor")}))
    return out


def record(pstore: PaperStore, rows: Sequence[tuple]) -> int:
    """Inserta solo lo nuevo (nunca reemplaza). Devuelve cuántas filas se añadieron."""
    if not rows:
        return 0
    n0 = pstore.execute("SELECT count(*) FROM paper_ledger")[0][0]
    ph = ", ".join("?" * len(COLS))
    pstore.executemany(f"INSERT OR IGNORE INTO paper_ledger VALUES ({ph})", list(rows))
    return int(pstore.execute("SELECT count(*) FROM paper_ledger")[0][0] - n0)


def query(pstore: PaperStore, symbol: str | None = None, scope: str | None = None,
          profile: str | None = None, limit: int = 500) -> list[dict]:
    where, params = [], []
    for col, val in (("symbol", symbol), ("scope", scope), ("profile", profile)):
        if val is not None:
            where.append(f"{col} = ?")
            params.append(val)
    sql = (f"SELECT {', '.join(c for c in COLS if c != 'payload')} FROM paper_ledger"
           + (" WHERE " + " AND ".join(where) if where else "")
           + " ORDER BY exit_t DESC, ledger_id LIMIT ?")
    cols = [c for c in COLS if c != "payload"]
    return [dict(zip(cols, r, strict=True)) for r in pstore.execute(sql, [*params, limit])]


def counts(pstore: PaperStore) -> dict[str, int]:
    rows = pstore.execute("SELECT scope, symbol, count(*) FROM paper_ledger GROUP BY 1, 2")
    return {f"{s}:{sym}": int(n) for s, sym, n in rows}
