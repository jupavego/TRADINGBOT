"""Registro de intentos del escáner en `scanner.duckdb` (T95). Lo usa `ScannerStore` (mezcla).

El almacén de validación de T49 (`paper.duckdb`) lo tiene abierto la API y DuckDB admite un solo
proceso escritor (la misma razón de `eim/validation/attempts.py`): los intentos del escáner viven
en la base del escáner, con el mismo contrato de familia —se registran todos, nunca se borran y
sin p cuentan como 1— y la corrección se hace sobre los previos de T49 más estos.

Tablas:

- `attempts`: una fila por intento `instrumento|agente@versión|marco|hN` (alta, última vez visto,
  último p bruto, con cuántas maduras se calculó y su Sharpe deflactado).
- `attempt_obs`: una observación por intento y vela de decisión (`cut_ms`): lado, cierre de
  partida, σ del horizonte, costo, cuándo madura (`end_cut_ms`) y, al madurar, el cierre final y
  los dos resultados (el del lado dicho y el del contrario). La de la síntesis guarda además las
  cuatro puntuaciones de la oportunidad, para calibrar los pesos del ranking hacia adelante.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence

ATTEMPTS_DDL = """
CREATE TABLE IF NOT EXISTS attempts (
    attempt_key VARCHAR PRIMARY KEY, instrument_id VARCHAR, symbol VARCHAR, agent_id VARCHAR,
    agent_version VARCHAR, timeframe VARCHAR, horizon_bars INTEGER, first_seen BIGINT,
    last_seen BIGINT, p_raw DOUBLE, p_at_n INTEGER, dsr DOUBLE);
CREATE TABLE IF NOT EXISTS attempt_obs (
    attempt_key VARCHAR, cut_ms BIGINT, end_cut_ms BIGINT, deep_run_id VARCHAR, symbol VARCHAR,
    timeframe VARCHAR, side INTEGER, close0 DOUBLE, sigma_h DOUBLE, cost DOUBLE,
    matured BOOLEAN, close_end DOUBLE, outcome DOUBLE, outcome_flip DOUBLE, scores_json VARCHAR,
    PRIMARY KEY (attempt_key, cut_ms));
"""


class AttemptRecords:
    """Mezcla de `ScannerStore`: usa su conexión (`_con`), su cerrojo (`_lock`) y `_q`/`_x`."""

    def record_attempts(self, deep_run_id: str, cut: int, step_ms: int,
                        attempts: Sequence) -> int:
        """Da de alta los intentos (idempotente) y una observación por intento y vela; devuelve
        cuántas observaciones nuevas hubo (repetir la misma pasada no duplica nada)."""
        if not attempts:
            return 0
        rows = [(a.key, a.instrument_id, a.symbol, a.agent_id, a.version, a.timeframe,
                 a.horizon_bars, cut, cut, None, 0, None) for a in attempts]
        obs = [(a.key, cut, cut + a.horizon_bars * step_ms, deep_run_id, a.symbol, a.timeframe,
                a.side, a.close0, a.sigma_h, a.cost, False, None, None, None,
                None if a.scores is None else json.dumps(a.scores, ensure_ascii=False))
               for a in attempts]
        with self._lock:
            before = self._con.execute("SELECT count(*) FROM attempt_obs").fetchone()[0]
            self._con.executemany(
                "INSERT OR IGNORE INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            self._con.executemany(
                "UPDATE attempts SET last_seen = ? WHERE attempt_key = ? AND last_seen < ?",
                [(cut, a.key, cut) for a in attempts])
            self._con.executemany(
                "INSERT OR IGNORE INTO attempt_obs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", obs)
            after = self._con.execute("SELECT count(*) FROM attempt_obs").fetchone()[0]
        return int(after - before)

    def pending_obs(self, upto_cut: int) -> list[dict]:
        """Observaciones con lado, σ y costo cuyo horizonte ya cerró (`end_cut_ms ≤ upto_cut`)."""
        rows = self._q("SELECT attempt_key, cut_ms, end_cut_ms, symbol, timeframe, side, close0, "
                       "sigma_h, cost FROM attempt_obs WHERE matured = FALSE AND side <> 0 AND "
                       "sigma_h IS NOT NULL AND cost IS NOT NULL AND end_cut_ms <= ? "
                       "ORDER BY symbol, end_cut_ms", [int(upto_cut)])
        keys = ("attempt_key", "cut_ms", "end_cut_ms", "symbol", "timeframe", "side", "close0",
                "sigma_h", "cost")
        return [dict(zip(keys, r, strict=True)) for r in rows]

    def mature_obs(self, rows: Iterable[tuple[str, int, float, float, float]]) -> int:
        """(clave, cut, cierre final, resultado, resultado contrario) → madura la observación."""
        data = [(c, o, f, k, int(t)) for k, t, c, o, f in rows]
        if not data:
            return 0
        with self._lock:
            self._con.executemany(
                "UPDATE attempt_obs SET matured = TRUE, close_end = ?, outcome = ?, "
                "outcome_flip = ? WHERE attempt_key = ? AND cut_ms = ?", data)
        return len(data)

    def stale_keys(self) -> list[str]:
        """Intentos cuyo nº de maduras cambió desde el último p calculado."""
        rows = self._q("SELECT a.attempt_key FROM attempts a JOIN (SELECT attempt_key, count(*) "
                       "AS n FROM attempt_obs WHERE matured = TRUE GROUP BY attempt_key) m "
                       "ON a.attempt_key = m.attempt_key WHERE m.n <> a.p_at_n "
                       "ORDER BY a.attempt_key")
        return [r[0] for r in rows]

    def matured_series(self, keys: Sequence[str]) -> dict[str, tuple[list[float], list[float]]]:
        out: dict[str, tuple[list[float], list[float]]] = {k: ([], []) for k in keys}
        if not keys:
            return out
        for k in keys:
            for o, f in self._q("SELECT outcome, outcome_flip FROM attempt_obs WHERE "
                                "attempt_key = ? AND matured = TRUE ORDER BY cut_ms", [k]):
                out[k][0].append(float(o))
                out[k][1].append(float(f))
        return out

    def set_stats(self, rows: Iterable[tuple[str, float | None, int, float | None]]) -> None:
        data = [(p, int(n), d, k) for k, p, n, d in rows]
        if data:
            with self._lock:
                self._con.executemany("UPDATE attempts SET p_raw = ?, p_at_n = ?, dsr = ? "
                                      "WHERE attempt_key = ?", data)

    def family(self) -> dict[str, float | None]:
        """Último p bruto de cada intento del escáner (None = sin p)."""
        return {k: (None if p is None else float(p))
                for k, p in self._q("SELECT attempt_key, p_raw FROM attempts")}

    def attempt_stats(self, keys: Sequence[str]) -> dict[str, dict]:
        out = {}
        for k in keys:
            r = self._q("SELECT a.p_raw, a.dsr, (SELECT count(*) FROM attempt_obs o WHERE "
                        "o.attempt_key = a.attempt_key), (SELECT count(*) FROM attempt_obs o "
                        "WHERE o.attempt_key = a.attempt_key AND o.matured = TRUE) FROM "
                        "attempts a WHERE a.attempt_key = ?", [k])
            if r:
                p, d, n, m = r[0]
                out[k] = {"p_raw": None if p is None else round(float(p), 6),
                          "dsr": None if d is None else round(float(d), 6), "n_obs": int(n),
                          "n_matured": int(m)}
        return out

    def synthesis_matured(self, agent_id: str = "sintesis") -> list[dict]:
        """Resultados maduros de la síntesis con sus puntuaciones (para `rank.calibrate`)."""
        rows = self._q("SELECT o.cut_ms, o.scores_json, o.outcome FROM attempt_obs o JOIN "
                       "attempts a ON a.attempt_key = o.attempt_key WHERE a.agent_id = ? AND "
                       "o.matured = TRUE AND o.scores_json IS NOT NULL ORDER BY o.cut_ms",
                       [agent_id])
        return [{"t": int(t), "scores": json.loads(s), "outcome": float(o)} for t, s, o in rows]

    def attempt_counts(self) -> Mapping[str, int]:
        a = self._q("SELECT count(*) FROM attempts")[0][0]
        o, m = self._q("SELECT count(*), sum(CASE WHEN matured = TRUE THEN 1 ELSE 0 END) FROM "
                       "attempt_obs")[0]
        return {"attempts": int(a), "observations": int(o), "matured": int(m or 0)}
