"""Evaluación de líderes (T41, I/O): almacén → scorecards (puros) → veredictos → tablero.

La corre el servicio de vigilancia cada pocos minutos (es el único proceso que puede abrir
`data/leaders.duckdb`) y la CLI `python -m eim.leaders score` con el vigilante apagado. El
tablero se guarda en `data/leaders/` (JSON) para la API y `build_snapshot`.
"""

from __future__ import annotations

import logging

from eim.copytrading import Board, ScoreParams, build_board, score
from eim.copytrading.board import position_changes
from eim.copytrading.forward import VerdictMark, cohorts, covered_ms
from eim.copytrading.scorecard import LeaderData, Scorecard
from eim.copytrading.trades import Trip
from eim.core.leaders import Leader
from eim.data.leader_store import LeaderStore
from eim.leaders.params import POSITIONS_MAX_AGE_MS

log = logging.getLogger(__name__)
PHOTO_STEP_MS = 15 * 60_000  # salto entre fotos que aún cuenta como tiempo capturado
PORTFOLIO_EVERY_MS = 6 * 3_600_000
HOUR_MS = 3_600_000
SOURCE = "hyperliquid:info+ws"


def n_trials(store: LeaderStore, p: ScoreParams) -> int:
    """Billeteras entre las que se eligió: registradas, universo visto en el descubrimiento
    (evidencia `universe`) y nunca menos que `min_trials`."""
    lds = store.leaders()
    universe = max((int(float(ld.evidence.get("universe", 0) or 0)) for ld in lds), default=0)
    return max(p.min_trials, len(lds), universe)


def gather(store: LeaderStore, ld: Leader, asof: int) -> LeaderData:
    """Todo lo capturado del líder conocido a `asof` (nunca posterior)."""
    times = store.photo_times(ld.id, asof)
    near = store.positions_near(ld.id, asof)
    positions = near[1] if near and asof - near[0] <= POSITIONS_MAX_AGE_MS else []
    pf = store.portfolio(ld.id)
    return LeaderData(
        leader=ld, fills=[f for f in store.fills_fast(ld.id) if f.observed_at <= asof],
        funding=[r for r in store.funding_rows(ld.id) if r.observed_at <= asof],
        positions=positions, portfolio=pf[1] if pf and pf[0] <= asof else None,
        quotes=store.follow_quotes(ld.id), forward_start=times[0] if times else None,
        observed_ms=covered_ms(times, PHOTO_STEP_MS))


def _photo_at(store: LeaderStore, lid: str, t: int) -> list | None:
    """Foto vigente en `t`; None si la última anterior es demasiado vieja (vigilante apagado):
    un «cambio en 1 h» contra una foto de ayer no sería un cambio en 1 h."""
    got = store.positions_near(lid, t)
    return got[1] if got is not None and t - got[0] <= PHOTO_STEP_MS else None


def _record(store: LeaderStore, cards: list[Scorecard], now: int) -> None:
    """Veredicto → estado del líder; cada cambio queda en el historial con sus motivos."""
    last: dict[str, str] = {m.leader_id: m.verdict for m in store.verdicts()}
    status = {ld.id: ld.status for ld in store.leaders()}
    for c in cards:
        if last.get(c.leader_id) != c.verdict:
            store.add_verdict(VerdictMark(leader_id=c.leader_id, t=now, verdict=c.verdict,
                                          quality=c.quality),
                              [r.text for r in c.reasons if r.kind != "aviso"])
        if status.get(c.leader_id) != c.verdict:
            store.set_status(c.leader_id, c.verdict, now)


def evaluate(store: LeaderStore, now: int, p: ScoreParams | None = None,
             record: bool = True) -> Board:
    """Puntúa a todos los líderes capturados (watch/approved/rejected) y arma el tablero."""
    p = p or ScoreParams()
    tracked = [ld for ld in store.leaders() if ld.tracked and ld.venue == "hyperliquid"]
    trials = n_trials(store, p)
    cards: list[Scorecard] = []
    fwd: dict[str, list[Trip]] = {}
    positions, positions_at, changes, errors = {}, {}, {}, []
    for ld in tracked:
        try:
            card, trips = score(gather(store, ld, now), trials, now, p)
        except Exception as exc:  # un líder con datos rotos no tumba el tablero
            errors.append(f"{ld.id}: {type(exc).__name__}: {exc}"[:300])
            log.exception("scorecard %s", ld.id)
            continue
        cards.append(card)
        fwd[ld.id] = trips
        near = store.positions_near(ld.id, now)
        if near is None:
            continue
        positions[ld.id], positions_at[ld.id] = near[1], near[0]
        changes[ld.id] = position_changes(near[1], {
            h: _photo_at(store, ld.id, now - int(h * HOUR_MS)) for h in p.change_windows_h})
    if record:
        _record(store, cards, now)
    return build_board(now, cards, trials, positions, positions_at, changes,
                       cohorts(store.verdicts(), fwd), p.summary(), {"leaders": SOURCE}, errors)


def refresh_portfolios(store: LeaderStore, info, now: int, limit: int | None = None,
                       max_age_ms: int = PORTFOLIO_EVERY_MS) -> int:
    """Pide `portfolio` (peso 20) a los líderes capturados sin cartera reciente."""
    n = 0
    for ld in store.leaders():
        if not ld.tracked or ld.venue != "hyperliquid" or (limit is not None and n >= limit):
            continue
        pf = store.portfolio(ld.id)
        if pf is not None and now - pf[0] < max_age_ms:
            continue
        store.save_portfolio(ld.id, now, info.portfolio(ld.address))
        n += 1
    return n
