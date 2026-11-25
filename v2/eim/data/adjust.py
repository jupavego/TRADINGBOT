"""Precio crudo frente a ajustado (T90): splits, dividendos y empalmes de futuros.

El almacén guarda SOLO la vela cruda, tal como la publicó la fuente, y los eventos aparte
(`corporate_actions`). La serie ajustada **se calcula al leer** y no se escribe nunca en el
mismo sitio que la cruda, así que no hay forma de mezclarlas: los agentes reciben la ajustada
(sin saltos artificiales que parezcan una caída del 50 %) y el backtest conoce las dos (la
cruda es la que se habría negociado ese día).

Método: ajuste hacia atrás, el de CRSP. La última vela no cambia y cada evento multiplica lo
anterior a su fecha ex por un factor:

- **split** `r` (acciones nuevas por cada vieja): precio × 1/r y volumen × r;
- **dividendo** `D` en efectivo: precio × (1 − D / cierre crudo previo); el volumen no cambia;
- **empalme** de un futuro continuo (`roll`, razón nuevo/viejo): precio × razón.

Funciones puras: entran velas y eventos, salen velas. Ni red ni disco.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import model_validator

from eim.core import Candle
from eim.core.market import Frozen

ADJUSTMENT_METHOD = "hacia atrás (CRSP): split 1/r, dividendo 1 − D/cierre previo, empalme ×razón"


class PriceEvent(Frozen):
    """Un evento que rompe la continuidad del precio crudo, con su fecha ex `t` (ms UTC).

    `split`: acciones nuevas por cada vieja. `dividend`: efectivo por acción. `roll`: razón
    precio del contrato nuevo / precio del viejo al empalmar. Los que no aplican, None.
    """

    t: int
    split: float | None = None
    dividend: float | None = None
    roll: float | None = None
    source: str = ""

    @model_validator(mode="after")
    def _check(self) -> PriceEvent:
        if self.split is None and self.dividend is None and self.roll is None:
            raise ValueError("un evento necesita split, dividend o roll")
        if self.split is not None and self.split <= 0:
            raise ValueError("split debe ser > 0")
        if self.dividend is not None and self.dividend < 0:
            raise ValueError("dividend no puede ser negativo")
        if self.roll is not None and self.roll <= 0:
            raise ValueError("roll debe ser > 0")
        return self


class Factor(Frozen):
    """Factor acumulado para las velas con `t` ANTERIOR a `until` (exclusivo)."""

    until: int
    price: float
    volume: float


def factors(raw: Sequence[Candle], events: Iterable[PriceEvent]) -> list[Factor]:
    """Factores acumulados hacia atrás, uno por evento con efecto, ordenados por `until`.

    El dividendo necesita el cierre crudo de la última vela anterior a su fecha ex; si no hay
    ninguna (el evento es anterior a la serie) no tiene efecto sobre nada y se omite.
    """
    evs = sorted(events, key=lambda e: e.t)
    ts = [c.t for c in raw]
    price, volume = 1.0, 1.0
    out: list[Factor] = []
    for ev in reversed(evs):
        p, v = 1.0, 1.0
        if ev.split is not None:
            p, v = p / ev.split, v * ev.split
        if ev.roll is not None:
            p *= ev.roll
        k = _last_before(ts, ev.t) if ev.dividend else None
        if k is not None:
            prev_close = raw[k].c
            if prev_close <= 0 or ev.dividend >= prev_close:
                raise ValueError(f"dividendo {ev.dividend} imposible con cierre previo "
                                 f"{prev_close} (t={ev.t})")
            p *= 1.0 - ev.dividend / prev_close
        if p == 1.0 and v == 1.0:
            continue
        price, volume = price * p, volume * v
        out.append(Factor(until=ev.t, price=price, volume=volume))
    return sorted(out, key=lambda f: f.until)


def factor_at(fs: Sequence[Factor], t: int) -> tuple[float, float]:
    """(factor de precio, factor de volumen) de una vela con apertura `t`."""
    for f in fs:                      # ordenados por `until`: el primero que la cubre manda
        if t < f.until:
            return f.price, f.volume
    return 1.0, 1.0


def adjust_candles(raw: Sequence[Candle], events: Iterable[PriceEvent]) -> list[Candle]:
    """Serie ajustada a partir de la cruda; la cruda no se toca y la última vela no cambia."""
    fs = factors(raw, events)
    if not fs:
        return list(raw)
    out = []
    for c in raw:
        p, v = factor_at(fs, c.t)
        if p == 1.0 and v == 1.0:
            out.append(c)
            continue
        tb = None if c.taker_buy_v is None else c.taker_buy_v * v
        out.append(Candle(t=c.t, o=c.o * p, h=c.h * p, l=c.l * p, c=c.c * p, v=c.v * v,
                          taker_buy_v=tb, trades=c.trades))
    return out


def describe(events: Iterable[PriceEvent]) -> str:
    """Resumen legible de lo que se ajustó («2 splits, 1 dividendo»), para `sources`."""
    evs = list(events)
    parts = []
    for attr, one, many in (("split", "split", "splits"), ("dividend", "dividendo", "dividendos"),
                            ("roll", "empalme", "empalmes")):
        n = sum(1 for e in evs if getattr(e, attr))
        if n:
            parts.append(f"{n} {one if n == 1 else many}")
    return ", ".join(parts) if parts else "sin eventos"


def _last_before(ts: Sequence[int], t: int) -> int | None:
    lo, hi = 0, len(ts)
    while lo < hi:
        mid = (lo + hi) // 2
        if ts[mid] < t:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1 if lo > 0 else None
