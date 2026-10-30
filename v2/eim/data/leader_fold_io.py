"""Evaluación incremental de líderes (T41, I/O): `leaders.duckdb` → `LeaderFold` por líder.

El servicio guarda un `EvalCache` entre vueltas: cada evaluación lee de cada líder solo lo nuevo
(ejecuciones con `observed_at` reciente y las cotizaciones de las patas en espera) en vez de todo
su historial, y lo lee con `LeaderStore.reader` (instantánea coherente, sin el candado de la
captura). Sin caché (CLI `score`) o al rehacer, el historial se lee moneda a moneda y en tandas
de `CHUNK`: una sola consulta con todo un líder de alta frecuencia (unión + orden de 2,1 M filas
con el tope de 1 GB de DuckDB) frenaba hasta 7 s las escrituras de la captura.

Un líder se rehace desde cero cuando lo leído no cuadra con lo plegado: otro número de
ejecuciones del esperado (unión de otro equipo T61, inserción tardía) o cotizaciones nuevas de
patas ya plegadas. Una moneda con un relleno anterior a lo aplicado se rehace sola. Así la
memoria no depende del tamaño del historial (2026-10-29: 10–13 GB → ver `docs/OPERACION.md`).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import NamedTuple

from eim.copytrading import ScoreParams
from eim.copytrading.forward import forward_trips
from eim.copytrading.scorecard import LeaderData, Scorecard, assemble
from eim.copytrading.trades import Trip
from eim.copytrading.trip_fold import FillRow, LeaderFold, Quote
from eim.core.leaders import Leader

QUOTE_FINAL_MS = 300_000  # `QuoteBook` graba la cotización ≤ ~61 s después: a los 5 min es final
MARGIN_MS = 120_000  # relectura hacia atrás: ejecución grabada justo después de la lectura previa
CHUNK = 5_000  # filas por tanda al leer un historial entero (cada tanda retiene el GIL)

_COLS = ("f.symbol, f.t, f.observed_at, f.tid, f.oid, f.side, f.action, f.size, f.price, "
         "f.start_position, f.end_position, f.fee, f.closed_pnl, f.crossed, f.liquidated, "
         "f.leverage, f.channel")
_ORDER = " ORDER BY f.symbol, f.t, f.observed_at, f.tid, f.oid"
_NEW_SQL = (f"SELECT {_COLS} FROM leader_fills f WHERE f.leader_id = ? AND f.observed_at <= ? "
            f"AND f.observed_at > ?{_ORDER}")
_SYMBOL_SQL = (  # la cotización de una ejecución es de su misma moneda (`QuoteBook`)
    f"SELECT {_COLS}, q.follow_at, q.quote_t, q.bid, q.ask, q.mid, q.src FROM leader_fills f "
    "LEFT JOIN (SELECT tid, oid, follow_at, quote_t, bid, ask, mid, src FROM leader_follow "
    "WHERE leader_id = ? AND symbol = ?) q ON q.tid = f.tid AND q.oid = f.oid "
    f"WHERE f.leader_id = ? AND f.observed_at <= ? AND f.symbol = ?{_ORDER}")


class FundingRow(NamedTuple):
    symbol: str
    t: int
    usdc: float


def _rows(cur, sql: str, params: list) -> Iterator[FillRow]:
    cur.execute(sql, params)
    while batch := cur.fetchmany(CHUNK):
        for r in batch:
            yield FillRow(*r)


def _symbol_rows(cur, lid: str, asof: int, symbol: str) -> Iterator[FillRow]:
    """Todas las ejecuciones de una moneda a `asof`, en orden, con su cotización si la hay."""
    return _rows(cur, _SYMBOL_SQL, [lid, symbol, lid, asof, symbol])


def _count(cur, sql: str, params: list) -> int:
    return cur.execute(sql, params).fetchone()[0]


@dataclass
class _State:
    fold: LeaderFold
    asof: int
    n_quotes: int  # cotizaciones con observed_at ≤ fold.final_before al plegar
    recent: dict[tuple[int, int], int]  # (tid, oid) → observed_at de lo leído hace < MARGIN_MS


class EvalCache:
    """Estado de la evaluación entre vueltas (uno por proceso; solo lo usa un hilo a la vez)."""

    def __init__(self, p: ScoreParams | None = None) -> None:
        self.p = p or ScoreParams()
        self.states: dict[str, _State] = {}
        self.rebuilds = 0  # líderes rehechos desde cero (arranque, uniones, desajustes)
        self.redone = 0  # monedas rehechas solas (relleno anterior a lo aplicado)

    def keep(self, ids: set[str]) -> None:
        for lid in [k for k in self.states if k not in ids]:
            del self.states[lid]

    def score(self, store, ld: Leader, asof: int, n_trials: int, d: LeaderData
              ) -> tuple[Scorecard, list[Trip]]:
        """Como `score(gather(...))`. `d` trae todo menos ejecuciones, funding y cotizaciones."""
        with store.reader() as cur:
            fold = self.fold(cur, ld.id, asof)
            funding = [FundingRow(*r) for r in cur.execute(
                "SELECT symbol, t, usdc FROM leader_funding WHERE leader_id = ? AND "
                "observed_at <= ? ORDER BY t", [ld.id, asof]).fetchall()]
        trips = fold.trips(funding)
        fwd = forward_trips(trips, d.forward_start)
        return assemble(d, trips, fwd, fold.copy_stats(fwd), n_trials, asof, self.p), fwd

    def fold(self, cur, lid: str, asof: int) -> LeaderFold:
        try:
            return self._fold(cur, lid, asof)
        except BaseException:
            self.states.pop(lid, None)  # plegado a medias: la próxima vuelta lo rehace
            raise

    def _fold(self, cur, lid: str, asof: int) -> LeaderFold:
        final = asof - QUOTE_FINAL_MS
        total = _count(cur, "SELECT count(*) FROM leader_fills WHERE leader_id = ? AND "
                            "observed_at <= ?", [lid, asof])
        st = self.states.get(lid)
        if st is not None and asof >= st.asof:
            rows = [r for r in _rows(cur, _NEW_SQL, [lid, asof, st.asof - MARGIN_MS])
                    if (r.tid, r.oid) not in st.recent]
            if st.fold.n + len(rows) == total and \
                    self._n_quotes(cur, lid, st.fold.final_before) == st.n_quotes:
                self._advance(cur, lid, st, rows, final, asof)
            else:
                st = None
        else:
            st = None
        if st is None:
            st = self.states[lid] = self._rebuild(cur, lid, final, asof)
        st.n_quotes = self._n_quotes(cur, lid, final)
        return st.fold

    def _n_quotes(self, cur, lid: str, upto: int) -> int:
        return _count(cur, "SELECT count(*) FROM leader_follow WHERE leader_id = ? AND "
                           "observed_at <= ?", [lid, upto])

    def _advance(self, cur, lid: str, st: _State, rows: list[FillRow], final: int,
                 asof: int) -> None:
        fold = st.fold
        quotes = {(r[0], r[1]): Quote(*r[2:]) for r in cur.execute(  # las de patas en espera
            "SELECT tid, oid, follow_at, quote_t, bid, ask, mid, src FROM leader_follow "
            "WHERE leader_id = ? AND observed_at > ?", [lid, fold.final_before]).fetchall()}
        fold.begin(final, quotes)
        redo = fold.stale(rows)
        for r in rows:
            fold.observe(r)
            if r.symbol not in redo:
                fold.apply(r)
        self.redone += len(redo)
        for sym in sorted(redo):
            fold.rebuild(sym, _symbol_rows(cur, lid, asof, sym))
        fold.settle()
        st.asof = asof
        st.recent = {k: o for k, o in st.recent.items() if o > asof - MARGIN_MS}
        st.recent.update({(r.tid, r.oid): r.observed_at for r in rows
                          if r.observed_at > asof - MARGIN_MS})

    def _rebuild(self, cur, lid: str, final: int, asof: int) -> _State:
        self.rebuilds += 1
        fold = LeaderFold(self.p)
        fold.begin(final, {})
        recent: dict[tuple[int, int], int] = {}
        for (sym,) in cur.execute("SELECT DISTINCT symbol FROM leader_fills WHERE leader_id = ? "
                                  "AND observed_at <= ? ORDER BY 1", [lid, asof]).fetchall():
            for r in _symbol_rows(cur, lid, asof, sym):
                fold.observe(r)
                fold.apply(r)
                if r.observed_at > asof - MARGIN_MS:
                    recent[(r.tid, r.oid)] = r.observed_at
        fold.settle()
        return _State(fold, asof, 0, recent)
