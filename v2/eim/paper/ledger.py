"""Libro de registro fijo del bróker simulado: lo que ocurrió en vivo, escrito una sola vez.

El Historial de `View` se RECALCULA en cada consulta con las reglas y costos vigentes: cambiar un
parámetro reescribe el pasado (ayer→hoy, 157 de 167 operaciones cambiaron de PnL al calibrar el
deslizamiento). Este libro es de solo adición: cuando una operación de origen `vivo` (decidida en
tiempo real) se cierra, se guarda con sus precios, costos y versiones de reglas y de mecánica y no
se vuelve a tocar (`INSERT OR IGNORE`). Dos alcances: `perfil` (la operación del libro de un perfil,
con su tamaño y PnL en USDT) y `sombra` (la idea evaluada sola, en R, para el aprendizaje).
Las reconstruidas por backtest (`origin = backtest`) no entran: no ocurrieron en vivo.

Desde T118 cada fila de perfil guarda también el capital realizado con el que se dimensionó y el
que dejó el cierre (`capital_before`/`capital_after`, de `account.capital`, la misma lectura que el
panel; NULL en las filas anteriores), y `reconcile` compara el libro con la vista de ahora: qué
operaciones del libro ya no reproduce la vista y cuáles reproduce con otro PnL o capital.
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
        "mech_version", "cost_params", "recorded_ms", "retro", "payload", "capital_before",
        "capital_after")
NEW_COLS = ("capital_before", "capital_after")      # T118: al final, para migrar con ALTER TABLE
_TYPES = ("VARCHAR PRIMARY KEY, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, "
          "VARCHAR, INTEGER, VARCHAR, BIGINT, BIGINT, BIGINT, DOUBLE, DOUBLE, DOUBLE, DOUBLE, "
          "VARCHAR, DOUBLE, DOUBLE, DOUBLE, DOUBLE, DOUBLE, DOUBLE, DOUBLE, DOUBLE, DOUBLE, "
          "BOOLEAN, DOUBLE, BOOLEAN, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, BIGINT, "
          "BOOLEAN, VARCHAR, DOUBLE, DOUBLE").split(", ")
DDL = ("CREATE TABLE IF NOT EXISTS paper_ledger (" +
       ", ".join(f"{c} {t}" for c, t in zip(COLS, _TYPES, strict=True)) + ")")


def ensure(pstore: PaperStore) -> None:
    pstore.execute(DDL)
    for c in NEW_COLS:     # un libro creado antes de T118: las filas viejas quedan en NULL
        pstore.execute(f"ALTER TABLE paper_ledger ADD COLUMN IF NOT EXISTS {c} DOUBLE")


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
        "capital_before": d.get("capital_before"), "capital_after": d.get("capital_after"),
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


PNL_TOL = 1e-6      # USDT: por debajo, el PnL de la vista y el del libro son el mismo


def reconcile(rows: Sequence[dict], books: dict[str, ProfileState]) -> dict[str, dict]:
    """Libro fijo frente a la vista, por perfil (mismo alcance: operaciones en vivo del símbolo).

    `rows` son las filas `perfil` del símbolo (`query`). Devuelve, por perfil: filas del libro,
    operaciones en vivo de la vista, cuántas del libro la vista ya no reproduce (`outside`, con su
    ventana de cierres), cuántas reproduce con otro PnL o motivo (`differ`) y si coinciden en
    número, PnL y capital (`match`). Una vista recalculada con otras reglas, otro almacén u otro
    capital inicial no coincide, y esto lo dice en vez de presentarla como la historia."""
    out: dict[str, dict] = {}
    for pid, st in books.items():
        led = {r["idea_id"]: r for r in rows if r["profile"] == pid}
        view = {t["id"]: t for t in st.trades if t.get("origin") == "vivo"}
        gone = [r for k, r in led.items() if k not in view]
        differ = [k for k, r in led.items() if k in view and (
            abs((r["pnl_usdt"] or 0.0) - view[k]["pnl"]) > PNL_TOL
            or r["reason"] != view[k]["reason"])]
        last = max(led.values(), key=lambda r: (r["exit_t"], r["ledger_id"]), default=None)
        cap = last.get("capital_after") if last else None
        seen = last is not None and last["idea_id"] in view
        vcap = view[last["idea_id"]].get("capital_after") if seen else None
        out[pid] = {
            "rows": len(led), "view_live": len(view), "outside": len(gone),
            "outside_from": min((r["exit_t"] for r in gone), default=None),
            "outside_to": max((r["exit_t"] for r in gone), default=None),
            "differ": len(differ), "missing": sum(1 for k in view if k not in led),
            "capital_after": cap, "view_capital_after": vcap,
            "match": not gone and not differ and len(led) == len(view)
            and (cap is None or vcap is None or abs(cap - vcap) <= PNL_TOL),
        }
    return out
