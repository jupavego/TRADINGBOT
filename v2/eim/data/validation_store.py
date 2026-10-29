"""Registro de intentos y veredictos de la puerta de validación (T49), en `data/paper.duckdb`.

- `val_versions`: cada `estrategia@marco@vN` evaluada alguna vez (alta, padre, origen, nota,
  retiro). Una huella nueva de una estrategia@marco = versión nueva; la anterior queda retirada
  pero sigue contando como intento (Holm).
- `val_windows`: ventanas de ajuste de cada versión (las de los ancestros se suman al leer).
- `val_verdicts`: historial de veredictos por criterio, símbolo, versión y `asof`.
Comparte conexión y candado con `PaperStore` (un solo proceso escritor).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace

from eim.data.paper_store import PaperStore
from eim.validation.lineage import (
    AUTO_ORIGIN,
    Declaration,
    Version,
    Window,
    auto_windows,
    find_declaration,
)

_DDL = (
    """CREATE TABLE IF NOT EXISTS val_versions (
        sid VARCHAR, n INTEGER, fingerprint VARCHAR, strategy VARCHAR, timeframe VARCHAR,
        created_ms BIGINT, parent INTEGER, origin VARCHAR, note VARCHAR, retired_ms BIGINT,
        PRIMARY KEY (sid, n))""",
    """CREATE TABLE IF NOT EXISTS val_windows (
        sid VARCHAR, n INTEGER, from_ms BIGINT, to_ms BIGINT, symbol VARCHAR, note VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS val_verdicts (
        criteria VARCHAR, symbol VARCHAR, sid VARCHAR, n INTEGER, asof_ms BIGINT,
        computed_ms BIGINT, fingerprint VARCHAR, verdict VARCHAR, n_oos INTEGER,
        p_raw DOUBLE, p_holm DOUBLE, payload VARCHAR,
        PRIMARY KEY (criteria, symbol, sid, n, asof_ms))""",
)
_VCOLS = ("sid, n, fingerprint, strategy, timeframe, created_ms, parent, origin, note, "
          "retired_ms")


class ValidationStore:
    def __init__(self, pstore: PaperStore) -> None:
        self.ps = pstore
        for ddl in _DDL:
            self.ps.execute(ddl)

    # --- versiones --------------------------------------------------------------------
    def versions(self, sid: str | None = None) -> list[Version]:
        q = f"SELECT {_VCOLS} FROM val_versions" + (" WHERE sid = ?" if sid else "")
        rows = self.ps.execute(q + " ORDER BY sid, n", [sid] if sid else [])
        wq = "SELECT sid, n, from_ms, to_ms, symbol, note FROM val_windows"
        ws: dict[tuple[str, int], list[Window]] = {}
        for s, n, a, b, sym, note in self.ps.execute(wq + (" WHERE sid = ?" if sid else ""),
                                                     [sid] if sid else []):
            ws.setdefault((s, int(n)), []).append(Window(int(a), int(b), sym, note or ""))
        return [Version(r[0], int(r[1]), r[2], r[3], r[4], int(r[5]),
                        None if r[6] is None else int(r[6]), r[7], r[8] or "",
                        None if r[9] is None else int(r[9]),
                        tuple(sorted(ws.get((r[0], int(r[1])), []),
                                     key=lambda w: (w.from_ms, w.to_ms))))
                for r in rows]

    def ensure(self, sid: str, strategy: str, timeframe: str, fingerprint: str, now_ms: int,
               decls: Sequence[Declaration] = ()) -> Version:
        """La versión de esta huella; si es nueva se registra (padre = la vigente) y la
        vigente se retira. Una huella ya vista vuelve a ser la vigente (misma versión)."""
        fam = self.versions(sid)
        current = next((v for v in fam if v.retired_ms is None), None)
        same = next((v for v in fam if v.fingerprint == fingerprint), None)
        if same is not None:
            if same.retired_ms is not None:
                self._retire(current, now_ms)
                self.ps.execute("UPDATE val_versions SET retired_ms = NULL WHERE sid = ? AND n = ?",
                                [sid, same.n])
                return replace(same, retired_ms=None)
            return same
        decl = find_declaration(decls, sid, fingerprint)
        origin, note, windows = ((decl.origin, decl.note, decl.windows) if decl else
                                 (AUTO_ORIGIN, "", auto_windows(now_ms)))
        n = max((v.n for v in fam), default=0) + 1
        parent = current.n if current else (fam[-1].n if fam else None)
        self._retire(current, now_ms)
        self.ps.execute(f"INSERT INTO val_versions ({_VCOLS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        [sid, n, fingerprint, strategy, timeframe, now_ms, parent, origin, note,
                         None])
        self.ps.executemany("INSERT INTO val_windows VALUES (?,?,?,?,?,?)",
                            [(sid, n, w.from_ms, w.to_ms, w.symbol, w.note) for w in windows])
        return Version(sid, n, fingerprint, strategy, timeframe, now_ms, parent, origin, note,
                       None, tuple(windows))

    def _retire(self, v: Version | None, now_ms: int) -> None:
        if v is not None:
            self.ps.execute("UPDATE val_versions SET retired_ms = ? WHERE sid = ? AND n = ?",
                            [now_ms, v.sid, v.n])

    # --- procedencia (T61) --------------------------------------------------------------
    def provenance(self) -> dict:
        """Qué aportó cada máquina a esta base (filas importadas por tabla y las descartadas por
        duplicadas), de `share_origin`/`import_log`. Vacío si nunca se importó. Los contextos son
        la evidencia: de ellos salen, deterministas, las ideas y operaciones de cada versión.
        Duplicadas = filas de la ÚLTIMA foto de esa máquina que ya estaban aquí por otra vía (no
        importadas de ella); conflictos, los de esa importación (T117: sumar todas las
        importaciones inflaba la cifra con cada foto nueva aunque los datos no cambiaran)."""
        have = {r[0] for r in self.ps.execute(
            "SELECT table_name FROM duckdb_tables() WHERE database_name = current_database()")}
        if not {"share_origin", "import_log"} <= have:
            return {}
        out: dict[str, dict[str, dict[str, int]]] = {}
        for tbl, m, n in self.ps.execute(
                "SELECT tbl, machine, count(*) FROM share_origin GROUP BY tbl, machine"):
            out.setdefault(m, {}).setdefault(tbl, {"imported": 0, "duplicates": 0,
                                                   "conflicts": 0})["imported"] = int(n)
        for tbl, m, seen, c in self.ps.execute(
                "SELECT tbl, src_machine, arg_max(n_new + n_dup + n_conflict, at_ms), "
                "arg_max(n_conflict, at_ms) FROM import_log GROUP BY tbl, src_machine"):
            row = out.setdefault(m, {}).setdefault(tbl, {"imported": 0, "duplicates": 0,
                                                         "conflicts": 0})
            row["duplicates"] = max(int(seen) - row["imported"] - int(c), 0)
            row["conflicts"] = int(c)
        return {"machines": out, "note": "filas aportadas por otras máquinas; duplicadas = de su "
                "última foto, las que ya estaban aquí (misma estrategia@marco@versión en la misma "
                "vela = la misma operación)"}

    # --- veredictos -------------------------------------------------------------------
    def save_verdicts(self, criteria: str, symbol: str, asof_ms: int, computed_ms: int,
                      verdicts: Sequence[dict]) -> None:
        rows = [(criteria, symbol, v["sid"], v["n"], asof_ms, computed_ms, v["fingerprint"],
                 v["verdict"], v["n_oos"], v["p_raw"], v["p_holm"],
                 json.dumps(v, ensure_ascii=False, separators=(",", ":")))
                for v in verdicts]
        self.ps.executemany("INSERT OR REPLACE INTO val_verdicts VALUES "
                            "(?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    def last_pvalues(self, criteria: str) -> dict[tuple[str, str, int], float | None]:
        """Último p bruto (V3) de cada intento ya evaluado, por (símbolo, sid, n)."""
        rows = self.ps.execute(
            "SELECT symbol, sid, n, arg_max(p_raw, asof_ms) FROM val_verdicts "
            "WHERE criteria = ? GROUP BY symbol, sid, n", [criteria])
        return {(s, sid, int(n)): (None if p is None else float(p)) for s, sid, n, p in rows}

    def latest(self, criteria: str, symbol: str) -> tuple[int | None, int | None, list[dict]]:
        """Veredictos vigentes: (asof, calculado, filas) del último `asof` calculado."""
        got = self.ps.execute("SELECT max(asof_ms) FROM val_verdicts WHERE criteria = ? AND "
                              "symbol = ?", [criteria, symbol])
        asof = got[0][0] if got else None
        if asof is None:
            return None, None, []
        rows = self.ps.execute("SELECT payload, computed_ms FROM val_verdicts WHERE "
                               "criteria = ? AND symbol = ? AND asof_ms = ? ORDER BY sid, n",
                               [criteria, symbol, asof])
        return (int(asof), max(int(r[1]) for r in rows) if rows else None,
                [json.loads(r[0]) for r in rows])

    def history(self, criteria: str, symbol: str, sid: str, limit: int = 200) -> list[dict]:
        rows = self.ps.execute(
            "SELECT asof_ms, n, verdict, n_oos, p_raw, p_holm FROM val_verdicts WHERE "
            "criteria = ? AND symbol = ? AND sid = ? ORDER BY asof_ms DESC LIMIT ?",
            [criteria, symbol, sid, limit])
        return [{"asof": int(a), "n": int(n), "verdict": v, "n_oos": int(k), "p_raw": p,
                 "p_holm": ph} for a, n, v, k, p, ph in rows]
