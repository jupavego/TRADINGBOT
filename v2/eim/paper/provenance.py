"""¿Qué equipo vivió cada operación del libro fijo? (T196, libro central entre equipos)

Desde T196 el libro fijo (`paper_ledger`) viaja en la experiencia compartida (T61): cada equipo
publica las operaciones que vivió y las demás las unen sin duplicar. La procedencia ya la guarda
la unión en `share_origin` (`tbl = 'paper_ledger'`, `key = ledger_id`, `machine`): una fila que
no está ahí la escribió este equipo. Esta pieza solo lee esa procedencia y la declara; no decide
qué cuenta (eso es `eim.paper.universe`).

Una vela es UNA operación aunque la vivan dos equipos: la clave `ledger_id` lleva la idea
(símbolo:marco:vela:estrategia), así que la segunda copia nunca entra (gana la local y, si su
resultado difiere, queda en `share_conflicts`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

LOCAL = "local"                 # escrita por este equipo
ALL, ONLY_LOCAL = "all", "local"
MACHINES = (ALL, ONLY_LOCAL)
LABEL = {ALL: "todos los equipos (libro central, T196)",
         ONLY_LOCAL: "solo lo vivido en este equipo"}

_HAS = ("SELECT count(*) FROM duckdb_tables() WHERE database_name = current_database() "
        "AND table_name = 'share_origin'")
_SQL = "SELECT key, machine FROM share_origin WHERE tbl = 'paper_ledger'"


def origins(pstore) -> dict[str, str]:
    """`ledger_id` → equipo de origen de las filas que trajo la experiencia compartida.

    Sin importaciones (la tabla `share_origin` aún no existe) devuelve `{}`: todo es local."""
    if not pstore.execute(_HAS)[0][0]:
        return {}
    return {str(k): str(m) for k, m in pstore.execute(_SQL)}


def annotate(rows: Iterable[Mapping], where: Mapping[str, str]) -> list[dict]:
    """Copia de las filas con `machine` (el equipo que la vivió, o `local`)."""
    return [{**r, "machine": where.get(str(r.get("ledger_id")), LOCAL)} for r in rows]


def keep(rows: Sequence[Mapping], machines: str) -> list[Mapping]:
    """`all` = libro central; `local` = solo lo de este equipo (p. ej. el cierre de T31)."""
    if machines not in MACHINES:
        raise ValueError(f"machines debe ser uno de {MACHINES}, no {machines!r}")
    if machines == ALL:
        return list(rows)
    return [r for r in rows if r.get("machine", LOCAL) == LOCAL]


def _f(x: object) -> float:
    try:
        return float(x) if x not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def by_machine(kept: Iterable[Mapping]) -> dict[str, dict]:
    """Lo que cuenta, por equipo de origen: cuántas, PnL, R total y acierto."""
    out: dict[str, dict] = {}
    for r in kept:
        b = out.setdefault(str(r.get("machine", LOCAL)),
                           {"n": 0, "pnl_usdt": 0.0, "total_r": 0.0, "wins": 0})
        b["n"] += 1
        b["pnl_usdt"] += _f(r.get("pnl_usdt"))
        b["total_r"] += _f(r.get("r"))
        b["wins"] += int(_f(r.get("r")) > 0)
    for b in out.values():
        b["win_rate"] = b["wins"] / b["n"] if b["n"] else None
    return dict(sorted(out.items()))
