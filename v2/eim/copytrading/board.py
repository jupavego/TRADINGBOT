"""Tablero de líderes (puro): ranking, posiciones, cambios recientes, cohortes y pesos.

Es lo que la evaluación guarda en `data/leaders/` y lo que leen la API (pestaña «Líderes») y
`build_snapshot` (agente `smart_money`). Modo Análisis: no hay órdenes (copiar es T42).
"""

from __future__ import annotations

from eim.copytrading.forward import Cohort
from eim.copytrading.scorecard import Scorecard
from eim.core.leaders import LeaderPosition, LeaderWeight, PositionChange
from eim.core.market import Frozen

LABEL = "El rendimiento pasado no garantiza resultados futuros"
_ORDER = {"approved": 0, "watch": 1, "rejected": 2}


class Board(Frozen):
    asof: int
    mode: str = "ANALISIS"
    label: str = LABEL
    n_trials: int
    params: dict[str, float | int] = {}
    leaders: list[Scorecard] = []  # ordenados (rank 1 = mejor)
    positions: dict[str, list[LeaderPosition]] = {}  # foto vigente por líder
    positions_at: dict[str, int] = {}  # observed_at de esa foto
    changes: dict[str, list[PositionChange]] = {}
    cohorts: dict[str, Cohort] = {}
    weights: list[LeaderWeight] = []  # solo aprobados
    sources: dict[str, str] = {}
    errors: list[str] = []


def _key(c: Scorecard) -> tuple:
    f, h = c.fwd, c.all
    return (_ORDER[c.verdict], -c.quality, -(f.dsr or 0.0), -(h.dsr or 0.0), -f.net, c.leader_id)


def rank(cards: list[Scorecard]) -> list[Scorecard]:
    """Aprobados por calidad, luego vigilancia y descartados por su evidencia adelante."""
    return [c.model_copy(update={"rank": i + 1}) for i, c in enumerate(sorted(cards, key=_key))]


def position_changes(now: list[LeaderPosition], past: dict[float, list[LeaderPosition] | None]
                     ) -> list[PositionChange]:
    """Cambio de la posición firmada por moneda en cada ventana (None = sin foto tan vieja)."""

    def signed(ps: list[LeaderPosition]) -> dict[str, float]:
        return {x.symbol: x.size if x.side == "long" else -x.size for x in ps}

    cur = signed(now)
    out = []
    for h, ps in sorted(past.items()):
        if ps is None:
            continue
        old = signed(ps)
        for sym in sorted(set(cur) | set(old)):
            a, b = old.get(sym, 0.0), cur.get(sym, 0.0)
            if a != b:
                out.append(PositionChange(symbol=sym, window_h=h, from_size=a, to_size=b))
    return out


def weights(cards: list[Scorecard], positions_at: dict[str, int],
            changes: dict[str, list[PositionChange]]) -> list[LeaderWeight]:
    return [LeaderWeight(leader_id=c.leader_id, label=c.label, quality=c.quality,
                         account_value=c.account_value, hold_ms=c.fwd.hold_ms or c.all.hold_ms,
                         scored_at=c.scored_at, positions_at=positions_at.get(c.leader_id),
                         changes=changes.get(c.leader_id, []))
            for c in cards if c.verdict == "approved" and c.quality > 0]


def build_board(asof: int, cards: list[Scorecard], n_trials: int,
                positions: dict[str, list[LeaderPosition]], positions_at: dict[str, int],
                changes: dict[str, list[PositionChange]], cohorts: dict[str, Cohort],
                params: dict[str, float | int], sources: dict[str, str] | None = None,
                errors: list[str] | None = None) -> Board:
    ranked = rank(cards)
    return Board(asof=asof, n_trials=n_trials, params=params, leaders=ranked,
                 positions=positions, positions_at=positions_at, changes=changes,
                 cohorts=cohorts, weights=weights(ranked, positions_at, changes),
                 sources=sources or {}, errors=errors or [])
