"""Patas de arbitraje (T45): orden con tiempo límite, persecución acotada y deshacer.

- `send`: orden LIMIT a precio protegido (mejor precio de la testnet ± `slip_bps`) que se espera
  hasta `leg_timeout_ms`; lo no llenado se cancela. Id determinista por posición
  (`eia-…-<rol><n>`) y reenvío solo si el exchange confirma que no existe (`ensure_order`). La
  orden se anota ANTES de enviarse; con la red caída → `LegUnknown` (la reconciliación decide).
- `pair`: primera pata → segunda por lo llenado (fills parciales incluidos), persiguiendo hasta
  `chase_tries` veces con un precio cada vez más amplio que nunca pasa el tope por pata
  incompleta → lo que quede descubierto se deshace en la primera pata con precio límite = tope
  sobre su precio de ejecución; si ni así llena, a mercado (nunca se deja una pata huérfana) y
  la pérdida sobre el tope se marca (`over_cap` → kill-switch en el ejecutor).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from eim.execution.arb_book import UNKNOWN, ArbOrder, ArbPosition
from eim.execution.broker import LIMIT, MARKET, BrokerError, NetworkError, OrderRejected, OrderSpec
from eim.execution.service import ensure_order

TAGS = {"abrir": "a", "cubrir": "b", "deshacer": "u", "cerrar": "c", "rebalanceo": "k",
        "recortar": "r", "mercado": "m"}


class EmptyBook(BrokerError):
    """Sin precio en el libro de la testnet: la pata no se puede valorar ni enviar."""


class LegUnknown(BrokerError):
    """Orden en estado desconocido (red): la reconciliación consulta su id más tarde."""


@dataclass(frozen=True)
class ExecParams:
    leg_timeout_ms: int = 5_000      # tiempo límite de cada orden
    poll_s: float = 0.25
    slip_bps: float = 10.0           # precio límite inicial: mejor precio ± esto
    chase_tries: int = 2             # reintentos de la segunda pata
    hedge_tol: float = 0.005         # redondeo de la cobertura (comisión en moneda base)
    max_venue_dev: float = 0.10      # precio de la testnet vs el de referencia del escáner
    min_futures_notional: float = 100.0  # mínimo de orden USDⓈ-M (BTCUSDT; ETH 20)
    retries: int = 3
    backoff: float = 0.5


@dataclass(frozen=True)
class LegOrder:
    market: str
    symbol: str
    side: int
    qty: float
    reduce_only: bool = False

    def reverse(self, qty: float) -> LegOrder:
        """Orden que deshace esta (en futuros, deshacer una apertura solo reduce)."""
        return LegOrder(self.market, self.symbol, -self.side, qty,
                        reduce_only=self.market == "usdm" and not self.reduce_only)


@dataclass
class PairResult:
    first: float = 0.0               # base movida en la primera pata
    second: float = 0.0
    reversed: float = 0.0            # base deshecha en la primera pata
    loss: float = 0.0                # USD perdidos al deshacer (frente al precio de la 1.ª)
    over_cap: bool = False
    issues: list[str] = field(default_factory=list)


class Legs:
    def __init__(self, brokers: dict[str, Any], p: ExecParams, sleep: Callable[[float], None],
                 clock: Callable[[], int], save: Callable[[], None]) -> None:
        self.brokers, self.p, self._sleep, self._clock, self._save = brokers, p, sleep, clock, save

    def base(self, market: str, symbol: str) -> str:
        return self.brokers["spot"].base_asset(symbol) if market == "spot" else ""

    def top(self, market: str, symbol: str) -> tuple[float, float]:
        t = self.brokers[market].book_top(symbol)
        if not t:
            raise EmptyBook(f"libro vacío en {symbol} ({market})")
        return t

    def price(self, o: LegOrder, bps: float) -> float:
        bid, ask = self.top(o.market, o.symbol)
        px = ask * (1 + bps / 1e4) if o.side > 0 else bid * (1 - bps / 1e4)
        return self.brokers[o.market].round_price(o.symbol, px)

    def send(self, pos: ArbPosition, o: LegOrder, price: float | None, role: str,
             kind: str = LIMIT) -> tuple[float, float | None]:
        """(base neta movida, precio medio). Lanza `LegUnknown` si no hay respuesta firme."""
        b, p = self.brokers[o.market], self.p
        rec = ArbOrder(pos.next_cid(TAGS.get(role.split()[0], "o")), o.market, o.symbol,
                       o.side, o.qty, price, role, t=self._clock())
        pos.orders.append(rec)
        self._save()
        spec = OrderSpec(rec.cid, o.symbol, o.side, kind, qty=o.qty,
                         price=price if kind == LIMIT else None, reduce_only=o.reduce_only)
        try:
            st = ensure_order(b, spec, p.retries, p.backoff, self._sleep)
        except OrderRejected as e:
            rec.status = "REJECTED"
            pos.events.append(f"{self._clock()} {role} {o.symbol} rechazada: {e}")
            self._save()
            return 0.0, None
        except NetworkError as e:
            rec.status = UNKNOWN
            self._save()
            raise LegUnknown(f"{role} {o.symbol} ({rec.cid}): {e}") from e
        polls = max(1, math.ceil(p.leg_timeout_ms / max(p.poll_s * 1000, 1.0)))
        deadline = self._clock() + p.leg_timeout_ms
        while st.is_open and polls > 0 and self._clock() <= deadline:
            polls -= 1
            self._sleep(p.poll_s)
            try:
                st = b.get_order(o.symbol, rec.cid, False) or st
            except NetworkError:
                continue
        if st.is_open:                                # tiempo límite: se cancela el resto
            try:
                b.cancel(o.symbol, rec.cid, False)
                st = b.get_order(o.symbol, rec.cid, False) or st
            except NetworkError as e:
                pos.apply(rec, st, self.base(o.market, o.symbol))
                rec.status = UNKNOWN
                self._save()
                raise LegUnknown(f"{role} {o.symbol} ({rec.cid}) sin cancelar: {e}") from e
        moved = pos.apply(rec, st, self.base(o.market, o.symbol))
        self._save()
        return moved, st.avg_price

    def trim(self, pos: ArbPosition, o: LegOrder, role: str, force: bool) -> float:
        """Una sola pata (corregir un descubierto o cerrar la que queda): LIMIT protegida y,
        con `force`, el resto a mercado. Devuelve la base movida."""
        if o.qty <= 0:
            return 0.0
        moved = 0.0
        try:
            moved = self.send(pos, o, self.price(o, self.p.slip_bps), role)[0]
        except EmptyBook as e:
            pos.events.append(f"{self._clock()} {e}")
        rest = self.brokers[o.market].round_qty(o.symbol, o.qty - moved)
        if force and rest > 0:
            moved += self.send(pos, replace(o, qty=rest), None, role, MARKET)[0]
        return moved

    def ordered(self, pos: ArbPosition, qty_fut: float, opening: bool,
                qty_spot: float | None = None) -> tuple[LegOrder, LegOrder]:
        """Patas en orden de envío: la que consume más del libro de la testnet primero."""
        s, f = pos.spot, pos.fut
        sgn = 1 if opening else -1
        orders = {"spot": LegOrder("spot", s.symbol, sgn * s.side,
                                   qty_fut if qty_spot is None else qty_spot),
                  "usdm": LegOrder("usdm", f.symbol, sgn * f.side, qty_fut,
                                   reduce_only=not opening)}
        frac: dict[str, float] = {}
        for m, o in orders.items():
            try:
                bids, asks = self.brokers[m].depth(o.symbol)
                depth = sum(q for _, q in (asks if o.side > 0 else bids))
                frac[m] = o.qty / depth if depth > 0 else float("inf")
            except BrokerError:
                frac = {}
                break
        seq = sorted(orders, key=lambda m: -frac[m]) if len(frac) == 2 else pos.order
        if opening:
            pos.order = list(seq)
        return orders[seq[0]], orders[seq[1]]

    def _hedge_qty(self, o: LegOrder, done: float) -> float:
        """Cantidad de la segunda pata para cubrir `done`, al paso de su símbolo."""
        b = self.brokers[o.market]
        lo = b.round_qty(o.symbol, done)
        hi = b.round_qty(o.symbol, done * (1 + self.p.hedge_tol))
        q = hi if done - lo > self.p.hedge_tol * done else lo
        return min(q, o.qty)

    def pair(self, pos: ArbPosition, first: LegOrder, second: LegOrder, cap_bps: float,
             urgent: bool, roles: tuple[str, str] = ("abrir", "cubrir")) -> PairResult:
        p, r = self.p, PairResult()
        px1 = self.price(first, p.slip_bps)              # libro vacío: no se envía nada
        self.top(second.market, second.symbol)
        r.first, avg1 = self.send(pos, first, px1, roles[0])
        rest1 = self.brokers[first.market].round_qty(first.symbol, first.qty - r.first)
        if urgent and rest1 > 0:                          # cierre urgente: la 1.ª entera
            r.first += self.send(pos, replace(first, qty=rest1), None, "mercado", MARKET)[0]
        if r.first <= 0:
            r.issues.append(f"primera pata {first.symbol} sin llenar")
            return r
        b2 = self.brokers[second.market]
        want = self._hedge_qty(second, r.first)
        tol = p.hedge_tol * want                          # p. ej. la comisión cobrada en base
        tries = 0
        while want - r.second > tol and tries <= p.chase_tries:
            bps = p.slip_bps + (cap_bps - p.slip_bps) * tries / max(p.chase_tries, 1)
            try:
                px2 = self.price(second, min(bps, cap_bps))
            except EmptyBook as e:
                r.issues.append(str(e))
                break
            q = b2.round_qty(second.symbol, want - r.second)
            if q <= 0:
                break
            r.second += self.send(pos, replace(second, qty=q), px2, roles[1])[0]
            tries += 1
        rest = b2.round_qty(second.symbol, want - r.second) if want - r.second > tol else 0.0
        if urgent and rest > 0:                           # cierre urgente: no se deshace
            r.second += self.send(pos, replace(second, qty=rest), None, "mercado", MARKET)[0]
        excess = r.first - r.second
        if want - r.second > tol and excess > p.hedge_tol * r.first and not urgent:
            r.issues.append(f"segunda pata {second.symbol} incompleta: {r.second:.6g} de "
                            f"{want:.6g}")
            r.reversed, r.loss, r.over_cap = self.reverse(pos, first, excess, avg1, cap_bps)
        return r

    def reverse(self, pos: ArbPosition, first: LegOrder, qty: float, avg1: float | None,
                cap_bps: float) -> tuple[float, float, bool]:
        """Deshace `qty` de la primera pata: (base deshecha, pérdida USD, ¿sobre el tope?)."""
        b = self.brokers[first.market]
        q = b.round_qty(first.symbol, qty)
        if q <= 0 or not avg1:
            return 0.0, 0.0, False
        rev = first.reverse(q)
        cap_px = b.round_price(first.symbol, avg1 * (1 + rev.side * cap_bps / 1e4))
        moved, avg = self.send(pos, rev, cap_px, "deshacer")
        fills = [(moved, avg or cap_px)] if moved > 0 else []
        over = False
        rest = b.round_qty(first.symbol, q - moved)
        if rest > 0:                                       # fuera del tope: a mercado
            m, a = self.send(pos, replace(rev, qty=rest), None, "deshacer mercado", MARKET)
            if m > 0:
                fills.append((m, a or cap_px))
            over = True
        done = sum(x for x, _ in fills)
        loss = sum(rev.side * (px - avg1) * x for x, px in fills)
        over = over or loss > cap_bps / 1e4 * avg1 * done + 1e-9
        return done, loss, over
