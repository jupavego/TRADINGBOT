"""Tablas de la evaluación de líderes (T41) dentro de `data/leaders.duckdb`.

- `leader_portfolio`: última respuesta de `portfolio` por líder (preselección).
- `leader_follow`: precio que habría obtenido un seguidor por ejecución (copiabilidad).
- `leader_verdicts`: cada cambio de veredicto con su hora (¿sirve el filtro?).
Se mezcla en `LeaderStore` (misma conexión y candado).
"""

from __future__ import annotations

import json

from eim.copytrading.forward import VerdictMark
from eim.core.leaders import FollowQuote, LeaderFill, LeaderFunding, LeaderPosition

SCORE_DDL = """
CREATE TABLE IF NOT EXISTS leader_portfolio (
    leader_id VARCHAR PRIMARY KEY, fetched_at BIGINT, payload VARCHAR);
CREATE TABLE IF NOT EXISTS leader_follow (
    leader_id VARCHAR, tid BIGINT, oid BIGINT, symbol VARCHAR, observed_at BIGINT, follow_at BIGINT,
    quote_t BIGINT, bid DOUBLE, ask DOUBLE, mid DOUBLE, src VARCHAR,
    PRIMARY KEY (leader_id, tid, oid));
CREATE TABLE IF NOT EXISTS leader_verdicts (
    leader_id VARCHAR, t BIGINT, verdict VARCHAR, quality DOUBLE, reasons VARCHAR,
    PRIMARY KEY (leader_id, t));
"""
_FOLLOW = ("leader_id, tid, oid, symbol, observed_at, follow_at, quote_t, bid, ask, mid, "
           "src")
_FILL_KEYS = ("leader_id", "tid", "oid", "address", "symbol", "side", "action", "size", "price",
              "start_position", "end_position", "fee", "fee_token", "closed_pnl", "crossed",
              "liquidated", "leverage", "t", "observed_at", "channel", "source")


class ScoreTables:
    """Métodos de T41 sobre `LeaderStore` (usa sus `_exec` e `_insert`)."""

    def _exec(self, q: str, params: list | tuple = ()) -> list[tuple]: ...  # LeaderStore

    def _insert(self, table: str, cols: str, rows: list[tuple], chunk: int = 400) -> int: ...

    # --- lectura rápida del historial ---------------------------------------------------------
    def fills_fast(self, lid: str) -> list[LeaderFill]:
        """Todas las ejecuciones del líder sin revalidar (ya se validaron al guardarlas)."""
        rows = self._exec(f"SELECT {', '.join(_FILL_KEYS)} FROM leader_fills WHERE "
                          "leader_id = ? ORDER BY t, observed_at", [lid])
        return [LeaderFill.model_construct(**dict(zip(_FILL_KEYS, r, strict=True)))
                for r in rows]

    def funding_rows(self, lid: str) -> list[LeaderFunding]:
        rows = self._exec("SELECT leader_id, symbol, usdc, rate, size, t, observed_at, source "
                          "FROM leader_funding WHERE leader_id = ? ORDER BY t", [lid])
        return [LeaderFunding.model_construct(leader_id=r[0], address=lid.split(":", 1)[-1],
                                              symbol=r[1], usdc=r[2], rate=r[3], size=r[4],
                                              t=r[5], observed_at=r[6], source=r[7])
                for r in rows]

    def photo_times(self, lid: str, asof: int) -> list[int]:
        """Horas de las fotos de posiciones: la primera marca el inicio del seguimiento
        adelante y los saltos entre ellas, el tiempo realmente cubierto."""
        return [r[0] for r in self._exec(
            "SELECT observed_at FROM leader_positions WHERE leader_id = ? AND observed_at <= ? "
            "ORDER BY observed_at", [lid, asof])]

    def positions_near(self, lid: str, asof: int) -> tuple[int, list[LeaderPosition]] | None:
        """Última foto con observed_at ≤ asof (sin límite de edad)."""
        row = self._exec("SELECT observed_at, positions FROM leader_positions WHERE "
                         "leader_id = ? AND observed_at <= ? ORDER BY observed_at DESC LIMIT 1",
                         [lid, asof])
        if not row:
            return None
        return row[0][0], [LeaderPosition.model_validate(p) for p in json.loads(row[0][1])]

    def recent_coins(self, since: int) -> set[str]:
        return {r[0] for r in self._exec(
            "SELECT DISTINCT symbol FROM leader_fills WHERE t >= ?", [since])}

    # --- cartera ------------------------------------------------------------------------------
    def save_portfolio(self, lid: str, fetched_at: int, payload: list) -> None:
        self._exec("INSERT INTO leader_portfolio VALUES (?, ?, ?) ON CONFLICT (leader_id) DO "
                   "UPDATE SET fetched_at = excluded.fetched_at, payload = excluded.payload",
                   [lid, fetched_at, json.dumps(payload)])

    def portfolio(self, lid: str) -> tuple[int, list] | None:
        row = self._exec("SELECT fetched_at, payload FROM leader_portfolio WHERE leader_id = ?",
                         [lid])
        return (row[0][0], json.loads(row[0][1])) if row else None

    # --- precio del seguidor ------------------------------------------------------------------
    def add_follow(self, quotes: list[FollowQuote]) -> int:
        return self._insert("leader_follow", _FOLLOW, [
            (q.leader_id, q.tid, q.oid, q.symbol, q.observed_at, q.follow_at, q.quote_t, q.bid,
             q.ask, q.mid, q.src) for q in quotes])

    def follow_quotes(self, lid: str) -> dict[tuple[int, int], FollowQuote]:
        keys = [c.strip() for c in _FOLLOW.split(",")]
        rows = self._exec(f"SELECT {_FOLLOW} FROM leader_follow WHERE leader_id = ?", [lid])
        return {(r[1], r[2]): FollowQuote(**dict(zip(keys, r, strict=True))) for r in rows}

    # --- veredictos ---------------------------------------------------------------------------
    def add_verdict(self, mark: VerdictMark, reasons: list[str]) -> None:
        self._insert("leader_verdicts", "leader_id, t, verdict, quality, reasons",
                     [(mark.leader_id, mark.t, mark.verdict, mark.quality,
                       json.dumps(reasons, ensure_ascii=False))])

    def verdicts(self) -> list[VerdictMark]:
        return [VerdictMark(leader_id=r[0], t=r[1], verdict=r[2], quality=r[3] or 0.0)
                for r in self._exec("SELECT leader_id, t, verdict, quality FROM "
                                    "leader_verdicts ORDER BY t, leader_id")]
