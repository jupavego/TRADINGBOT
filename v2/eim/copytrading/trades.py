"""Operaciones de plano a plano (puro): ejecuciones de un líder → viajes con su neto.

Un viaje empieza cuando la posición de una moneda sale de 0 y termina al volver a 0 (cierre)
o al cruzar de lado (giro: cierra el viaje viejo y abre otro con el resto). Neto = PnL
cerrado del exchange − comisiones + funding cobrado durante el viaje. Si la primera ejecución
vista ya parte de una posición, el viaje es **parcial** (su apertura es anterior a nuestro
historial) y no entra en las estadísticas.

`SymbolTrips` arma los viajes de una moneda ejecución a ejecución: `build_trips` lo usa con
todo el historial de una vez y la evaluación incremental (`trip_fold.py`) lo conserva entre
vueltas y le pasa solo lo nuevo.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from eim.core.leaders import LeaderFill, LeaderFunding, Side


@dataclass(frozen=True)
class Leg:
    """Parte de una ejecución que pertenece a un viaje (un giro reparte la suya en dos)."""

    fill: LeaderFill
    qty: float
    buy: bool  # dirección de la orden: compra (long abre/aumenta, short reduce/cierra)


@dataclass
class Trip:
    symbol: str
    side: Side
    t_open: int
    complete: bool  # se vio la apertura
    t_close: int | None = None
    before_history: bool = False  # ya estaba abierta en la primera ejecución vista
    legs: list[Leg] = field(default_factory=list)
    pnl: float = 0.0
    fees: float = 0.0
    funding: float = 0.0
    size_max: float = 0.0
    notional_max: float = 0.0
    first_size: float = 0.0
    avg_downs: int = 0
    leverage_max: float | None = None
    liquidated: bool = False
    _in_qty: float = 0.0
    _in_cost: float = 0.0
    _out_qty: float = 0.0
    _out_cost: float = 0.0
    _pos: float = 0.0
    _n_legs: int = 0  # patas aplicadas (la evaluación incremental no las guarda todas)
    _n_taker: int = 0

    @property
    def closed(self) -> bool:
        return self.t_close is not None

    @property
    def net(self) -> float:
        return self.pnl - self.fees + self.funding

    @property
    def entry(self) -> float:
        return self._in_cost / self._in_qty if self._in_qty else 0.0

    @property
    def exit(self) -> float:
        return self._out_cost / self._out_qty if self._out_qty else 0.0

    @property
    def hold_ms(self) -> int | None:
        return self.t_close - self.t_open if self.t_close is not None else None

    @property
    def taker_share(self) -> float:
        return self._n_taker / self._n_legs if self._n_legs else 0.0

    def add_in(self, f: LeaderFill, qty: float, fee: float, tol: float) -> None:
        if self._in_qty and self.complete:
            e = self.entry
            worse = f.price < e * (1 - tol) if self.side == "long" else f.price > e * (1 + tol)
            self.avg_downs += worse
        if not self._n_legs or not self.first_size:
            self.first_size = qty
        self._in_qty += qty
        self._in_cost += qty * f.price
        self._pos += qty
        self._touch(f, qty, fee, buy=self.side == "long")
        self.size_max = max(self.size_max, self._pos)
        self.notional_max = max(self.notional_max, self._pos * f.price)

    def add_out(self, f: LeaderFill, qty: float, fee: float, pnl: float) -> None:
        self._out_qty += qty
        self._out_cost += qty * f.price
        self._pos = max(0.0, self._pos - qty)
        self.pnl += pnl
        self._touch(f, qty, fee, buy=self.side == "short")

    def _touch(self, f: LeaderFill, qty: float, fee: float, buy: bool) -> None:
        self.legs.append(Leg(f, qty, buy))
        self._n_legs += 1
        self._n_taker += f.crossed
        self.fees += fee
        self.liquidated |= f.liquidated
        if f.leverage is not None:
            self.leverage_max = max(self.leverage_max or 0.0, f.leverage)


class SymbolTrips:
    """Viajes de UNA moneda, alimentados en orden (t, observed_at, tid). Las ejecuciones del
    mismo milisegundo esperan juntas en `_group` hasta que llega otra hora (o `flush`): se
    encadenan por posición antes de aplicarse. `on_legs(trip)` se llama tras cada ejecución
    con los viajes que recibieron patas (la evaluación incremental las pliega y las suelta)."""

    def __init__(self, symbol: str, avg_down_tol: float = 0.002,
                 on_legs: Callable[[Trip], None] | None = None,
                 trip_cls: type[Trip] = Trip) -> None:
        self.symbol, self.tol = symbol, avg_down_tol
        self.done: list[Trip] = []
        self.cur: Trip | None = None
        self.prev: float | None = None  # posición final de la última ejecución aplicada
        self.last_t: int | None = None  # hora del último grupo aplicado
        self._group: list[LeaderFill] = []
        self._on_legs, self._cls = on_legs, trip_cls

    def add(self, f: LeaderFill) -> None:
        if self._group and f.t != self._group[0].t:
            self.flush()
        self._group.append(f)

    def flush(self) -> None:
        if not self._group:
            return
        group, self._group = self._group, []
        self.last_t = group[0].t
        for f in _chain_group(group, self.prev):
            n = len(self.done)
            self._step(f)
            if self._on_legs is not None:  # terminados en este paso (con o sin pata) y el abierto
                for tr in self.done[n:]:
                    self._on_legs(tr)
                if self.cur is not None:
                    self._on_legs(self.cur)

    def trips(self) -> list[Trip]:
        """Cerrados y cortados en orden, y el abierto al final."""
        self.flush()
        return self.done + ([self.cur] if self.cur is not None else [])

    def _step(self, f: LeaderFill) -> None:
        sym, tol, cur = self.symbol, self.tol, self.cur
        s, e = f.start_position, f.end_position
        if self.prev is not None and not _same(s, self.prev):
            if cur is not None:  # la posición no sigue a la anterior: hueco en los datos
                cur.complete = False
                self.done.append(cur)
            cur = None
        if cur is None and s != 0:  # posición abierta antes de lo visto (o tras un hueco)
            cur = self._cls(sym, "long" if s > 0 else "short", f.t, complete=False,
                            before_history=self.prev is None, _pos=abs(s))
        self.prev = e
        if f.action == "open" or cur is None:
            if cur is not None:  # apertura sin cierre previo: hueco en los datos
                cur.complete = False
                self.done.append(cur)
            cur = self._cls(sym, f.side, f.t, complete=True)
            cur.add_in(f, abs(e), f.fee, tol)
        elif f.action == "increase":
            cur.add_in(f, f.size, f.fee, tol)
        elif f.action == "reduce":
            cur.add_out(f, f.size, f.fee, f.closed_pnl)
        else:  # close o flip: termina el viaje
            old = abs(s)
            share = old / f.size if f.size else 1.0
            cur.add_out(f, old, f.fee * share, f.closed_pnl)
            cur.t_close = f.t
            self.done.append(cur)
            cur = None
            if f.action == "flip":
                cur = self._cls(sym, "long" if e > 0 else "short", f.t, complete=True)
                cur.add_in(f, abs(e), f.fee * (1 - share), tol)
        self.cur = cur


def build_trips(fills: list[LeaderFill], funding: list[LeaderFunding] | None = None,
                avg_down_tol: float = 0.002) -> list[Trip]:
    """Viajes por moneda en orden temporal (cerrados y abiertos). `fills` de un solo líder."""
    by_sym: dict[str, SymbolTrips] = {}
    for f in sorted(fills, key=lambda f: (f.t, f.observed_at, f.tid)):
        b = by_sym.get(f.symbol)
        if b is None:
            b = by_sym[f.symbol] = SymbolTrips(f.symbol, avg_down_tol)
        b.add(f)
    trips = [tr for b in by_sym.values() for tr in b.trips()]
    _assign_funding(trips, funding or [])
    return sorted(trips, key=lambda tr: (tr.t_open, tr.symbol))


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a))


def _chain_group(group: list[LeaderFill], cur: float | None) -> list[LeaderFill]:
    """Un milisegundo, siguiendo la cadena posición inicial → final desde `cur` (el `tid` no
    la respeta). Sin continuación posible se toma la que no continúa a ninguna otra del grupo
    (o la primera restante)."""
    group, out = list(group), []
    while group:
        k = next((n for n, f in enumerate(group)
                  if cur is not None and _same(f.start_position, cur)), None)
        if k is None:  # inicio del grupo: el que no continúa a ningún otro del grupo
            ends = [f.end_position for f in group]
            k = next((n for n, f in enumerate(group)
                      if not any(_same(f.start_position, e) for e in ends)), 0)
        f = group.pop(k)
        out.append(f)
        cur = f.end_position
    return out


def _chained(fs: list[LeaderFill]) -> list[LeaderFill]:
    """Orden temporal; dentro del mismo milisegundo, encadenado por posición (`_chain_group`)."""
    out: list[LeaderFill] = []
    i = 0
    while i < len(fs):
        j = i
        while j < len(fs) and fs[j].t == fs[i].t:
            j += 1
        out += _chain_group(fs[i:j], out[-1].end_position if out else None)
        i = j
    return out


def _assign_funding(trips: list[Trip], funding: list[LeaderFunding]) -> None:
    """Cada pago va al viaje de esa moneda abierto en ese instante (`t_open < t ≤ t_close`);
    un viaje parcial cubre también lo anterior a su primera ejecución vista."""
    by_sym: dict[str, list[Trip]] = defaultdict(list)
    for tr in trips:
        by_sym[tr.symbol].append(tr)
    starts = {s: [0 if tr.before_history else tr.t_open for tr in ts]
              for s, ts in by_sym.items()}
    for row in funding:
        ts = by_sym.get(row.symbol)
        if not ts:
            continue
        i = bisect.bisect_left(starts[row.symbol], row.t) - 1
        if i >= 0 and (ts[i].t_close is None or row.t <= ts[i].t_close):
            ts[i].funding += row.usdc
