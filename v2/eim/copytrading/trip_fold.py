"""Viajes y copiabilidad de un líder plegados de forma incremental (T41, puro).

`build_trips` + `copy_stats` sobre todo el historial ocupan memoria y tiempo proporcionales a
él: con un líder de alta frecuencia (2,1 M de ejecuciones y 1,8 M de cotizaciones del seguidor
el 2026-10-29) el servicio retenía 10–13 GB y la evaluación pasaba los 15 min del vigilante.
`LeaderFold` aplica cada ejecución UNA vez (`SymbolTrips` por moneda) y pliega cada pata en el
`TripFollow` de su viaje en cuanto su cotización es definitiva: llegó, o ya no puede llegar
(`observed_at` ≤ `final_before`). No guarda ejecuciones ni patas viejas, solo cifras: un viaje
sin patas por operación y las latencias en vivo (8 B cada una). Da lo mismo que `score` sobre
el historial completo (`tests/copytrading/test_trip_fold.py`).

Quien lo alimenta (`eim/data/leader_fold_io.py`) garantiza el orden: lo nuevo de una moneda va
por `apply` solo si es posterior a lo aplicado; si no, `rebuild` la rehace entera.
"""

from __future__ import annotations

from array import array
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import NamedTuple

from eim.copytrading.copyability import CopyStats, TripFollow, finish, latency_stats
from eim.copytrading.params import ScoreParams
from eim.copytrading.trades import SymbolTrips, Trip, _assign_funding


class Quote(NamedTuple):
    """Lo que `TripFollow` lee de un `FollowQuote`."""

    follow_at: int
    quote_t: int
    bid: float | None
    ask: float | None
    mid: float
    src: str


class FillRow(NamedTuple):
    """Ejecución como la lee la evaluación (lo que usan `SymbolTrips` y `TripFollow`), con la
    cotización del seguidor si ya estaba grabada (`q_*`)."""

    symbol: str
    t: int
    observed_at: int
    tid: int
    oid: int
    side: str
    action: str
    size: float
    price: float
    start_position: float
    end_position: float
    fee: float
    closed_pnl: float
    crossed: bool
    liquidated: bool
    leverage: float | None
    channel: str
    q_follow_at: int | None = None
    q_quote_t: int | None = None
    q_bid: float | None = None
    q_ask: float | None = None
    q_mid: float | None = None
    q_src: str | None = None

    def quote(self) -> Quote | None:
        if self.q_src is None:
            return None
        return Quote(self.q_follow_at, self.q_quote_t, self.q_bid, self.q_ask, self.q_mid,
                     self.q_src)


@dataclass(eq=False)
class FoldTrip(Trip):
    """`Trip` con su seguidor plegado: `legs` guarda solo las patas aún sin cotización
    definitiva (las demás ya están en `follow`)."""

    follow: TripFollow = field(default_factory=TripFollow)


@dataclass
class _Sym:
    trips: SymbolTrips
    pending: dict[int, FoldTrip] = field(default_factory=dict)  # id → viaje con patas en espera


class LeaderFold:
    def __init__(self, p: ScoreParams) -> None:
        self.p = p
        self.syms: dict[str, _Sym] = {}
        self.latency: dict[str, array] = {}  # canal → latencias en vivo (ms)
        self.taker = [0, 0]  # (tomadoras, ejecuciones) fuera del historial reenviado
        self.n = 0  # ejecuciones contadas
        self.final_before = 0  # pata con observed_at ≤ esto y sin cotización: ya no llegará
        self.quotes: dict[tuple[int, int], Quote] = {}  # recientes, para las patas en espera

    def begin(self, final_before: int, quotes: dict[tuple[int, int], Quote]) -> None:
        self.final_before, self.quotes = final_before, quotes

    # --- alimentación -----------------------------------------------------------------------
    def observe(self, r: FillRow) -> None:
        """Cuenta una ejecución nueva en la latencia y la proporción tomadora (sin orden)."""
        self.n += 1
        if r.channel == "ws_snapshot":
            return
        self.taker[0] += r.crossed
        self.taker[1] += 1
        lat = r.observed_at - r.t
        if 0 <= lat <= self.p.live_max_latency_ms:
            xs = self.latency.get(r.channel)
            if xs is None:
                xs = self.latency[r.channel] = array("d")
            xs.append(float(lat))

    def stale(self, rows: Iterable[FillRow]) -> set[str]:
        """Monedas con algo nuevo no posterior a lo ya aplicado (relleno de un hueco o el mismo
        milisegundo): hay que rehacerlas con `rebuild`."""
        out = set()
        for r in rows:
            s = self.syms.get(r.symbol)
            if s is None:
                continue
            s.trips.flush()
            if s.trips.last_t is not None and r.t <= s.trips.last_t:
                out.add(r.symbol)
        return out

    def apply(self, r: FillRow) -> None:
        """Ejecución nueva, posterior a lo aplicado de su moneda, en orden (t, observed_at, tid)."""
        s = self.syms.get(r.symbol)
        if s is None:
            s = self.syms[r.symbol] = self._new(r.symbol)
        s.trips.add(r)

    def rebuild(self, symbol: str, rows: Iterable[FillRow]) -> None:
        """Rehace los viajes de una moneda con TODAS sus ejecuciones en orden (no las cuentas:
        esas ejecuciones ya pasaron por `observe`)."""
        s = self.syms[symbol] = self._new(symbol)
        for r in rows:
            s.trips.add(r)
        s.trips.flush()

    def settle(self) -> None:
        """Vuelve a mirar las patas en espera (llegó su cotización o pasó su plazo)."""
        for s in self.syms.values():
            s.trips.flush()
            for tr in list(s.pending.values()):
                self._drain(tr)

    def _new(self, symbol: str) -> _Sym:
        return _Sym(SymbolTrips(symbol, self.p.avg_down_tol, self._drain, FoldTrip))

    def _quote(self, f: FillRow) -> Quote | None:
        q = f.quote()
        return q if q is not None else self.quotes.get((f.tid, f.oid))

    def _drain(self, tr: FoldTrip) -> None:
        """Pliega las patas de la cabeza con cotización definitiva; las demás esperan (en orden,
        para sumar igual que `copy_stats`)."""
        legs, k = tr.legs, 0
        while k < len(legs):
            f = legs[k].fill
            q = self._quote(f)
            if q is None and f.observed_at > self.final_before:
                break
            tr.follow.add(legs[k], q, self.p)
            k += 1
        if k:
            del legs[:k]
        pending = self.syms[tr.symbol].pending
        if legs:
            pending[id(tr)] = tr
        else:
            pending.pop(id(tr), None)

    # --- resultados -------------------------------------------------------------------------
    def trips(self, funding: list) -> list[Trip]:
        """Como `build_trips`: en orden (apertura, moneda) y con el funding recién repartido
        (`funding` con `symbol`, `t`, `usdc`, en orden de `t`)."""
        out = [tr for s in self.syms.values() for tr in s.trips.trips()]
        for tr in out:
            tr.funding = 0.0
        _assign_funding(out, funding)
        return sorted(out, key=lambda tr: (tr.t_open, tr.symbol))

    def copy_stats(self, fwd: list[Trip]) -> CopyStats:
        """Como `copy_stats` sobre todo el historial con las cotizaciones de ahora."""
        follows = []
        for tr in fwd:
            if not (tr.closed and tr.complete):
                continue
            acc = tr.follow
            if tr.legs:  # patas en espera: tal como `copy_stats` las vería en este momento
                acc = acc.copy()
                for leg in tr.legs:
                    acc.add(leg, self._quote(leg.fill), self.p)
            follows.append((tr, acc))
        for ch, xs in self.latency.items():  # ordenadas: la próxima vez solo se ordena lo nuevo
            self.latency[ch] = array("d", sorted(xs))
        return finish(follows, latency_stats(self.latency), (self.taker[0], self.taker[1]),
                      self.p)
