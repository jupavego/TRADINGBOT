"""Replicador (puro): cambio de posición del líder → órdenes propias proporcionales (T42).

Objetivo = posición del líder × proporción (capital asignado / cuenta del líder, fijada al
abrir cada viaje del líder). Acción = diferencia entre objetivo y posición propia, con reglas:
- Nunca contra el movimiento del líder: si él aumenta, solo abrimos/aumentamos; si reduce,
  solo reducimos/cerramos (un aumento omitido no se «recupera» vendiendo menos).
- Cierre o giro del líder → cierre total propio, siempre (reduce-only).
- Topes por moneda y por líder (fracción del capital), redondeo hacia cero al paso del
  exchange y orden por debajo del mínimo → no se envía (el cierre total sí).
- Deslizamiento máximo: no se abre ni aumenta si nuestro precio queda más de X % peor que la
  entrada media del líder en ese viaje.
- Viaje excluido (abierto antes de seguirlo, apertura no vista o cerrado por nuestro stop):
  no se copia hasta que el líder vuelva a plano o gire.
`note` dice por qué la posición propia queda distinta del objetivo: la reconciliación separa
así la diferencia explicada de la no explicada. El motor de riesgo actúa después (motor).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Literal

from eim.copytrading.copy_models import ExecQuote, Signal
from eim.copytrading.copy_params import CopyParams, ExchangeSpec
from eim.core.market import Frozen

Kind = Literal["open", "increase", "reduce", "close"]
EXCLUDED_TEXT = {
    "preexistente": "posición abierta antes de seguirlo (no se copia salvo decisión explícita)",
    "apertura_no_vista": "viaje del líder sin apertura vista: no se copia a medias",
    "stop": "viaje cerrado por nuestro stop de protección: no se reabre",
    "kill": "viaje cerrado por el kill-switch de la subcuenta",
}


def sgn(x: float) -> int:
    return (x > 0) - (x < 0)


def same(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


@dataclass
class CoinCopy:
    """Estado de la copia de una moneda del líder."""

    coin: str
    leader: float = 0.0  # posición firmada del líder (última señal procesada)
    leader_entry: float = 0.0  # precio medio del líder en el viaje actual
    trip_t: int | None = None  # hora de apertura del viaje del líder
    ratio: float | None = None  # proporción fijada al abrir el viaje
    excluded: str | None = None
    note: str | None = None

    def target(self, leader: float | None = None) -> float:
        lp = self.leader if leader is None else leader
        return 0.0 if self.excluded or self.ratio is None else lp * self.ratio

    def to_dict(self) -> dict:
        return asdict(self)


class Action(Frozen):
    coin: str
    kind: Kind
    side: int  # dirección de la orden: +1 compra, −1 venta
    qty: float  # > 0, ya redondeada al paso
    target: float  # posición propia firmada tras la orden
    notes: tuple[str, ...] = ()

    @property
    def grows(self) -> bool:
        return self.kind in ("open", "increase")


class Skip(Frozen):
    coin: str
    code: str
    text: str
    kind: str = ""  # acción que se intentaba


class Ctx(Frozen):
    """Cuenta y mercado al decidir."""

    t: int
    equity: float  # capital de la subcuenta, marcado a mercado
    leader_av: float | None  # valor de la cuenta del líder
    quote: ExecQuote | None  # precio propio en el instante de la orden
    other_notional: float = 0.0  # nocional propio en las demás monedas


class Decision(Frozen):
    actions: list[Action] = []
    skips: list[Skip] = []
    target: float = 0.0  # objetivo sin topes (líder × proporción)
    ratio: float | None = None
    note: str | None = None  # motivo de que la posición propia quede ≠ objetivo
    new_trip: bool = False
    trip_end: bool = False


def _close(coin: str, own: float, notes: tuple[str, ...] = ()) -> Action:
    return Action(coin=coin, kind="close", side=-sgn(own), qty=abs(own), target=0.0, notes=notes)


def decide(c: CoinCopy, own: float, sig: Signal, ctx: Ctx, p: CopyParams, spec: ExchangeSpec
           ) -> tuple[Decision, CoinCopy]:
    """Acciones para una señal. Devuelve la decisión y el estado nuevo de la moneda."""
    c = replace(c)
    coin, new = c.coin, sig.end
    acts: list[Action] = []
    trip_end = False
    if not same(sig.start, c.leader) and c.leader != 0 and sgn(sig.start) != sgn(c.leader):
        # el viaje que copiábamos terminó sin que lo viéramos: se cierra y no se sigue el otro
        if own != 0:
            acts.append(_close(coin, own, ("el líder cerró sin señal vista",)))
            own = 0.0
        c, trip_end = CoinCopy(coin), True
    # ejecuciones intermedias no vistas (mismo lado): se sigue el cambio NETO desde la última
    # posición vista; la señal puede ser un aumento tras una gran reducción que no llegó
    gap = c.leader != 0 and not same(sig.start, c.leader)
    old = c.leader if gap else sig.start
    if new == 0 or (old != 0 and sgn(new) != sgn(old)):  # cierre o giro del líder
        if own != 0:
            acts.append(_close(coin, own))
            own = 0.0
        c, trip_end = CoinCopy(coin, leader=0.0), True
        if new == 0:
            return Decision(actions=acts, trip_end=True), c
        old = 0.0
    new_trip = c.trip_t is None
    if new_trip:  # misma clave que los viajes de T41: hora de la ejecución que lo abre
        c.trip_t, c.leader_entry = sig.open_t or sig.t, sig.vwap
        if old != 0:
            c.excluded = "apertura_no_vista"
    elif abs(new) > abs(old):
        add = abs(new) - abs(old)
        c.leader_entry = (abs(old) * c.leader_entry + add * sig.vwap) / abs(new)
    c.leader = new
    if c.excluded:
        skip = Skip(coin=coin, code=f"excluido:{c.excluded}", text=EXCLUDED_TEXT.get(
            c.excluded, c.excluded))
        return Decision(actions=acts, skips=[skip], new_trip=new_trip, trip_end=trip_end), c
    if c.ratio is None:
        if not ctx.leader_av or ctx.leader_av <= 0:
            s = Skip(coin=coin, code="sin_cuenta", text="sin valor de cuenta del líder: no se "
                     "puede fijar la proporción", kind="open")
            c.note = s.text
            return Decision(actions=acts, skips=[s], new_trip=new_trip, trip_end=trip_end,
                            note=s.text), c
        c.ratio = ctx.equity * p.alloc_frac / ctx.leader_av
    target = new * c.ratio
    grow = new_trip or abs(new) > abs(old)
    fn = _grow if grow else _shrink
    more, skips, note = fn(c, own, target, sig, ctx, p, spec)
    if gap and note is None:
        note = "ejecuciones intermedias no vistas: se siguió el cambio neto del líder"
    c.note = note
    return Decision(actions=acts + more, skips=skips, target=target, note=note, ratio=c.ratio,
                    new_trip=new_trip, trip_end=trip_end), c


def _caps(target: float, px: float, ctx: Ctx, p: CopyParams) -> tuple[float, list[str]]:
    lim, why = abs(target), []
    asset = p.max_asset_frac * ctx.equity / px
    room = max(0.0, p.max_leader_frac * ctx.equity - ctx.other_notional) / px
    if lim > asset:
        lim = asset
        why.append(f"tope por moneda: nocional ≤ {p.max_asset_frac:.0%} del capital")
    if lim > room:
        lim = room
        why.append(f"tope por líder: nocional total ≤ {p.max_leader_frac:.0%} del capital")
    return lim, why


def _grow(c: CoinCopy, own: float, target: float, sig: Signal, ctx: Ctx, p: CopyParams,
          spec: ExchangeSpec) -> tuple[list[Action], list[Skip], str | None]:
    coin, side = c.coin, sgn(target)
    kind: Kind = "increase" if own != 0 else "open"

    def skip(code: str, text: str) -> tuple[list[Action], list[Skip], str]:
        return [], [Skip(coin=coin, code=code, text=text, kind=kind)], text

    if abs(own) >= abs(target):
        return [], [], c.note  # ya tenemos lo que toca (o más, por un recorte previo)
    if ctx.quote is None:
        return skip("sin_precio", "sin precio del seguidor en el instante de la orden")
    if spec.step(coin) is None:
        return skip("sin_especificacion", f"{coin}: sin paso de cantidad del exchange")
    px = ctx.quote.mid
    lim, why = _caps(target, px, ctx, p)
    qty = spec.round_down(coin, lim - abs(own))
    if qty <= 0:
        return skip("tope" if why else "redondeo",
                    "; ".join(why) or "diferencia menor que el paso de cantidad")
    if qty * px < spec.min_notional:
        return skip("bajo_minimo", f"orden de {qty * px:,.2f} USD por debajo del mínimo "
                    f"de {spec.min_notional:,.0f} USD")
    exec_px = ctx.quote.price(side, p.half_spread)
    adverse = (exec_px - c.leader_entry) / c.leader_entry * side
    if adverse > p.max_slippage:
        return skip("deslizamiento", f"precio {exec_px:,.6g} a {adverse:.2%} en contra de la "
                    f"entrada del líder {c.leader_entry:,.6g} (máx. {p.max_slippage:.2%})")
    new_abs = abs(own) + qty
    gap = spec.round_down(coin, abs(target) - new_abs)
    note = "; ".join(why) if why else ("resto menor que el paso" if gap > 0 else None)
    act = Action(coin=coin, kind=kind, side=side, qty=qty, target=side * new_abs,
                 notes=tuple(why))
    return [act], [], note


def _shrink(c: CoinCopy, own: float, target: float, sig: Signal, ctx: Ctx, p: CopyParams,
            spec: ExchangeSpec) -> tuple[list[Action], list[Skip], str | None]:
    coin = c.coin
    if own == 0 or abs(own) <= abs(target):  # nada que reducir (un aumento omitido antes…)
        under = spec.round_down(coin, abs(target) - abs(own)) > 0
        return [], [], c.note or ("propia por debajo del objetivo: solo se compra cuando el "
                                  "líder aumenta" if under else None)
    px = ctx.quote.mid if ctx.quote is not None else sig.vwap
    rest = abs(target)
    if spec.round_down(coin, rest) <= 0 or rest * px < spec.min_notional:
        if not p.close_below_min and abs(own) * px < spec.min_notional:
            text = f"cierre de {abs(own) * px:,.2f} USD por debajo del mínimo"
            return [], [Skip(coin=coin, code="bajo_minimo", text=text, kind="close")], text
        why = "resto bajo el mínimo del exchange: cierre total" if rest > 0 else ""
        return [_close(coin, own, (why,) if why else ())], [], why or None
    qty = spec.round_down(coin, abs(own) - rest)
    if qty <= 0:
        return [], [], "diferencia menor que el paso de cantidad"
    if qty * px < spec.min_notional:
        text = (f"reducción de {qty * px:,.2f} USD por debajo del mínimo de "
                f"{spec.min_notional:,.0f} USD")
        return [], [Skip(coin=coin, code="bajo_minimo", text=text, kind="reduce")], text
    left = abs(own) - qty
    act = Action(coin=coin, kind="reduce", side=-sgn(own), qty=qty, target=sgn(own) * left)
    gap = spec.round_down(coin, left - rest)
    return [act], [], ("resto menor que el paso" if gap > 0 else None)
