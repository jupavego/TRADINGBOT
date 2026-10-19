"""Qué viaja en la experiencia compartida (T61) y con qué regla de unión.

Clasificación (decisión del usuario 2026-10-18, `PLAN/T61.md`):
- `keyed`: clave natural; misma clave y contenido (sin las columnas `volatile`) distinto =
  conflicto (se conserva lo local, se registra, nunca se pisa en silencio).
- `counter`: tiene un contador local (`seq`); se une por contenido y se reasigna el contador.
- `versions`: `val_versions`/`val_windows` (se unen por `(sid, huella)`, ver `share_versions`).
- No viajan: lo reproducible (velas, funding, calendario, biblioteca), lo derivado
  (`val_verdicts`, `forecasts`, tablero de líderes) y el estado de la máquina (kill-switch,
  latidos, `copy_state`, libro de la subcuenta, `op_*`, `risk_decisions`) ni los secretos.
"""

from __future__ import annotations

from dataclasses import dataclass

FORMAT = 1
SCHEMA_VERSION = 1      # sube si cambia la forma de lo exportado; se rechazan los mayores
LOG_DDL = (
    """CREATE TABLE IF NOT EXISTS import_log (
        import_id VARCHAR, at_ms BIGINT, tbl VARCHAR, src_machine VARCHAR, src_created VARCHAR,
        n_new BIGINT, n_dup BIGINT, n_conflict BIGINT, n_incompatible BIGINT,
        by_machine VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS share_origin (
        tbl VARCHAR, key VARCHAR, machine VARCHAR, import_id VARCHAR, PRIMARY KEY (tbl, key))""",
    """CREATE TABLE IF NOT EXISTS share_conflicts (
        import_id VARCHAR, tbl VARCHAR, key VARCHAR, src_machine VARCHAR, differs VARCHAR,
        remote_row VARCHAR)""",
)


@dataclass(frozen=True)
class Spec:
    db: str                       # archivo de la base (sin ruta)
    name: str                     # tabla
    kind: str                     # keyed | counter | versions
    key: tuple[str, ...] = ()     # columnas de la identidad
    volatile: tuple[str, ...] = ()  # no cuentan para decidir «conflicto» (tiempos locales)
    note: str = ""


REPORTS, PAPER, LEADERS = "reports.duckdb", "paper.duckdb", "leaders.duckdb"
SPECS: tuple[Spec, ...] = (
    Spec(REPORTS, "reports", "keyed", ("symbol", "timeframe", "agent_id", "version", "asof_ms")),
    Spec(REPORTS, "sim_trades", "keyed", ("id",)),
    Spec(PAPER, "paper_ctx", "keyed", ("symbol", "timeframe", "asof_ms"),
         ("origin", "created_ms"), "contexto por vela: de él salen, deterministas, las ideas"),
    Spec(PAPER, "val_versions", "versions"),
    Spec(PAPER, "val_windows", "versions"),
    Spec(LEADERS, "leaders", "keyed", ("id",),
         ("label", "status", "discovered_at", "updated_at", "evidence"),
         "registro de líderes; lo local manda en etiqueta y estado"),
    Spec(LEADERS, "leader_fills", "keyed", ("leader_id", "tid", "oid"),
         ("observed_at", "channel", "source")),
    Spec(LEADERS, "leader_funding", "keyed", ("leader_id", "symbol", "t"),
         ("observed_at", "source")),
    Spec(LEADERS, "leader_leverage", "keyed", ("leader_id", "symbol", "t"), ("observed_at",)),
    Spec(LEADERS, "leader_positions", "keyed", ("leader_id", "observed_at"), (),
         "fotos en vivo: no se reproducen"),
    Spec(LEADERS, "leader_follow", "keyed", ("leader_id", "tid", "oid"),
         ("observed_at", "follow_at", "quote_t", "bid", "ask", "mid", "src"),
         "precio del seguidor grabado en vivo; la misma ejecución = la misma fila"),
    Spec(LEADERS, "leader_recon", "keyed", ("machine", "leader_id", "observed_at"),
         ("t", "checked", "skipped", "size_ok", "match", "resynced", "diffs", "clock_offset_ms",
          "retries")),
    Spec(LEADERS, "leader_gaps", "keyed", ("machine", "leader_id", "symbol", "t_from", "t_to",
                                           "cause"), ("detail", "observed_at", "recovered")),
    Spec(LEADERS, "copy_journal", "counter", ("leader_id", "t", "kind", "coin", "code", "text"),
         ("seq", "data")),
)
DB_ORDER = (REPORTS, PAPER, LEADERS)
NOT_SHARED = {
    "candles/funding/calendar/biblioteca": "reproducible: cada máquina lo vuelve a descargar",
    "val_verdicts, forecasts, leader_verdicts, leader_portfolio": "derivado: se recalcula",
    "kill_switch.json, operation/, copy_state, op_alerts, op_equity, risk_decisions":
        "estado de la máquina: nunca se mezcla",
    "obs.duckdb (observatorio, T73)": "derivado de los JSONL de cada máquina: no viaja",
    ".env, claves": "secretos: nunca se exportan",
}


def specs_of(db: str) -> list[Spec]:
    return [s for s in SPECS if s.db == db]
