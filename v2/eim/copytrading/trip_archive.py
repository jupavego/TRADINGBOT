"""Archivo de lo viejo de un líder (T128, puro): hasta dónde se puede cortar y qué se guarda.

`leaders.duckdb` crecía ~110 MB al día y el 85 % de sus ejecuciones era de un solo líder
rechazado de alta frecuencia (grupo de control de T41). De los rechazados se conservan 7 días
de detalle; lo anterior se pliega una vez en una `SymbolBase` por moneda (viajes con su
seguidor y las cuentas de latencia, tomadoras y ejecuciones) y la evaluación arranca de ahí
(`LeaderFold.restore`) con el mismo resultado que sobre el historial completo
(`tests/copytrading/test_trip_archive.py`).

El corte de una moneda es el último instante ≤ límite sin patas a la espera de su cotización:
todo lo anterior está plegado del todo. Si la posición seguía abierta, su viaje se archiva tal
cual (`SymbolBase.open`, sin patas) y la evaluación lo sigue desde ahí. Antes (hasta el
2026-11-10) solo se cortaba con la posición plana, y un líder que nunca la cerraba del todo no
se podaba nunca: la base siguió creciendo ~87 MB al día con todo el crecimiento en los
rechazados. Lo archivado queda fijo con los parámetros de entonces (`params_of`): cambiarlos no
rehace lo archivado.
"""

from __future__ import annotations

from array import array
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from eim.copytrading.copyability import TripFollow
from eim.copytrading.params import ScoreParams
from eim.copytrading.trades import SymbolTrips
from eim.copytrading.trip_fold import FillRow, FoldTrip, LeaderFold, SymbolBase, _Sym

PARAM_KEYS = ("avg_down_tol", "live_max_latency_ms", "quote_timeout_ms", "follower_taker_fee",
              "allmids_half_spread")  # los que quedan dentro de viajes, seguidor y latencias


def params_of(p: ScoreParams) -> dict[str, float]:
    return {k: getattr(p, k) for k in PARAM_KEYS}


@dataclass
class Counts:
    """Las cuentas de `LeaderFold.observe` de un tramo de ejecuciones, con las latencias como
    histograma (son milisegundos enteros: guardarlas así no pierde nada)."""

    n: int = 0
    taker_x: int = 0
    taker_n: int = 0
    latency: dict[str, Counter[int]] = field(default_factory=dict)

    @classmethod
    def of(cls, base: SymbolBase | None) -> Counts:
        if base is None:
            return cls()
        return cls(base.n, base.taker[0], base.taker[1],
                   {ch: Counter(h) for ch, h in base.latency.items()})

    def observe(self, r: FillRow, p: ScoreParams) -> None:
        self.n += 1
        if r.channel == "ws_snapshot":
            return
        self.taker_x += r.crossed
        self.taker_n += 1
        lat = r.observed_at - r.t
        if 0 <= lat <= p.live_max_latency_ms:
            self.latency.setdefault(r.channel, Counter())[lat] += 1

    def merge(self, o: Counts) -> None:
        self.n += o.n
        self.taker_x += o.taker_x
        self.taker_n += o.taker_n
        for ch, c in o.latency.items():
            self.latency.setdefault(ch, Counter()).update(c)


def _ready(st: SymbolTrips, s: _Sym) -> bool:
    """Tras aplicar el grupo en curso: ¿se puede cortar aquí? (nada en espera de cotización)"""
    st.flush()
    return not s.pending


def _mark(tr: FoldTrip | None) -> tuple | None:
    """Estado del viaje abierto en un posible corte, sin copiar sus deslizamientos: la lista solo
    crece, así que basta su longitud (copiarla en cada grupo sería cuadrático con un viaje de
    miles de patas)."""
    if tr is None:
        return None
    f = tr.follow
    return (replace(tr, legs=[], follow=TripFollow()), f.slips, len(f.slips),
            (f.ok, f.stale, f.quoted, dict(f.src), f.cash, f.fees))


def _unmark(mark: tuple | None) -> FoldTrip | None:
    if mark is None:
        return None
    tr, slips, n, (ok, stale, quoted, src, cash, fees) = mark
    tr.follow = TripFollow(ok, stale, quoted, src, array("d", slips[:n]), cash, fees)
    return tr


def advance(base: SymbolBase | None, symbol: str, rows: Iterable[FillRow], final: int,
            p: ScoreParams, max_rows: int | None = None) -> SymbolBase | None:
    """Base nueva de `symbol`: `base` (o nada) más `rows` (las de la moneda posteriores a su
    corte y anteriores al límite, en el orden de la evaluación) hasta el último instante en que
    se puede cortar. `final` como en `LeaderFold.begin`. Con `max_rows` se para en el primer
    corte posible tras esas filas (transacciones acotadas). None si no hay ninguno."""
    fold = LeaderFold(p)
    fold.begin(final, {})
    if base is not None:
        fold.bases[symbol] = base
    s = fold.syms[symbol] = fold._new(symbol)
    st = s.trips
    kept, tail = Counts.of(base), Counts()
    best: tuple[int, int, float | None, tuple | None] | None = None
    group_t, seen = None, 0
    for r in rows:
        if r.t != group_t:
            if group_t is not None and _ready(st, s):
                kept.merge(tail)
                tail = Counts()
                best = (group_t, len(st.done), st.prev, _mark(st.cur))
                if max_rows is not None and seen >= max_rows:
                    break
            group_t = r.t
        tail.observe(r, p)
        fold.apply(r)
        seen += 1
    else:
        if group_t is not None and _ready(st, s):
            kept.merge(tail)
            best = (group_t, len(st.done), st.prev, _mark(st.cur))
    if best is None:
        return None
    cut_t, k, prev, mark = best
    return SymbolBase(symbol, cut_t, prev, st.done[:k], kept.n, (kept.taker_x, kept.taker_n),
                      {ch: dict(c) for ch, c in kept.latency.items()}, _unmark(mark))
