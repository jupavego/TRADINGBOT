"""Flujo de datos de usuario (T83): fills y cancelaciones **por evento**, no por sondeo.

- `parse_user_event` traduce los mensajes del flujo `listenKey` de Binance USDⓈ-M
  (`ORDER_TRADE_UPDATE`, `ACCOUNT_UPDATE`, `listenKeyExpired`) a `UserEvent` normalizados.
- `SimUserStream` produce los mismos eventos desde el `SimBroker` (`on_update`), en cola: se
  reparten con `pump`, fuera de la llamada al bróker, como llegan por la red. `connected=False`
  simula un corte: los eventos de ese tramo se pierden (la reconciliación los recupera).
- `UserEventRouter` reparte: las órdenes `eih-` al carril HFT y, para el carril direccional
  (T30), cada evento de una operación activa o de posición de su símbolo dispara `sync` al
  instante. Cierra el BACKLOG T30 (1): si el SL cierra la posición mientras la entrada LIMIT
  sigue viva, el evento de cuenta la cancela en ese momento (antes esperaba a la siguiente
  reconciliación y podía reabrir una posición sin SL).

La conexión WebSocket y el `listenKey` viven en `user_stream_ws.py`.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from eim.execution.broker import (
    CANCELED,
    CLIENT_PREFIX,
    EXPIRED,
    HFT_PREFIX,
    BrokerError,
    OrderState,
    trade_key,
)
from eim.execution.service import ExecutionService
from eim.execution.sim_broker import SimBroker
from eim.observability import hooks_service

_STATUS = {"EXPIRED_IN_MATCH": EXPIRED, "TRIGGERED": "TRIGGERED", "FINISHED": "TRIGGERED"}
_KIND = {"STOP_MARKET": "STOP", "TAKE_PROFIT_MARKET": "TAKE_PROFIT"}


@dataclass(frozen=True)
class UserEvent:
    kind: str                         # order | account | expired | other
    E: int                            # ms del evento (reloj del exchange)
    T: int = 0                        # ms de la transacción
    symbol: str = ""
    state: OrderState | None = None   # estado acumulado de la orden tras el evento
    exec_type: str = ""               # NEW | TRADE | CANCELED | EXPIRED | AMENDMENT…
    last_qty: float = 0.0             # cantidad llenada en ESTE evento
    last_price: float | None = None
    fee: float = 0.0
    fee_asset: str = ""
    maker: bool | None = None
    position: float | None = None     # ACCOUNT_UPDATE: posición del símbolo (con signo)
    entry_price: float | None = None


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def parse_user_event(msg: dict) -> list[UserEvent]:
    """Un mensaje del flujo de usuario → eventos (uno por posición en `ACCOUNT_UPDATE`)."""
    e, t_ev = msg.get("e", ""), int(msg.get("E") or 0)
    if e == "ORDER_TRADE_UPDATE":
        o = msg.get("o") or {}
        filled = _f(o.get("z"))
        kind = o.get("ot") or o.get("o") or ""
        st = OrderState(
            client_id=str(o.get("c", "")), symbol=str(o.get("s", "")),
            side=1 if o.get("S") == "BUY" else -1, kind=_KIND.get(kind, kind),
            status=_STATUS.get(o.get("X", ""), o.get("X", "")), qty=_f(o.get("q")) or None,
            filled=filled, avg_price=(_f(o.get("ap")) or None) if filled else None,
            trigger=_f(o.get("sp")) or None, close_position=bool(o.get("cp")),
            reduce_only=bool(o.get("R")), exchange_id=str(o.get("i", "")),
            fee=_f(o.get("n")), fee_asset=str(o.get("N") or ""))
        last = _f(o.get("l"))
        return [UserEvent("order", t_ev, int(msg.get("T") or o.get("T") or t_ev), st.symbol, st,
                          str(o.get("x", "")), last, (_f(o.get("L")) or None) if last else None,
                          _f(o.get("n")), str(o.get("N") or ""),
                          bool(o.get("m")) if "m" in o else None)]
    if e == "ACCOUNT_UPDATE":
        rows = (msg.get("a") or {}).get("P") or []
        return [UserEvent("account", t_ev, int(msg.get("T") or t_ev), str(p.get("s", "")),
                          position=_f(p.get("pa")), entry_price=_f(p.get("ep")) or None)
                for p in rows if p.get("ps", "BOTH") == "BOTH"]
    if e == "listenKeyExpired":
        return [UserEvent("expired", t_ev)]
    return [UserEvent("other", t_ev)]


class SimUserStream:
    """Flujo de usuario del `SimBroker`, con la misma forma que el de Binance."""

    def __init__(self, sim: SimBroker, clock: Callable[[], int]) -> None:
        self.sim, self._clock = sim, clock
        self.queue: deque[UserEvent] = deque()
        self.connected = True
        self.lost = 0                                  # eventos perdidos durante cortes
        sim.on_update = self._on_update

    def _on_update(self, new: OrderState, old: OrderState | None) -> None:
        same = old is not None and old.exchange_id == new.exchange_id
        prev = old.filled if same and old is not None else 0.0
        dq = round(new.filled - prev, 12)
        last_px = None
        if dq > 0 and new.avg_price is not None:
            prev_cost = (old.avg_price or 0.0) * prev if same and old is not None else 0.0
            last_px = (new.avg_price * new.filled - prev_cost) / dq
        exec_type = "TRADE" if dq > 0 else {CANCELED: "CANCELED", EXPIRED: "EXPIRED"}.get(
            new.status, "NEW" if not same else new.status)
        t = self._clock()
        evs = [UserEvent("order", t, t, new.symbol, new, exec_type, max(dq, 0.0), last_px,
                         dq * last_px * self.sim.fee_rate if last_px else 0.0, "USDT")]
        if dq > 0:
            pos = self.sim.position(new.symbol)
            evs.append(UserEvent("account", t, t, new.symbol, position=pos.qty,
                                 entry_price=pos.entry_price))
        if not self.connected:
            self.lost += len(evs)
            return
        self.queue.extend(evs)

    def pump(self, handler: Callable[[list[UserEvent]], None]) -> int:
        """Reparte los eventos en cola (también los que generen los propios manejadores)."""
        n = 0
        while self.queue:
            handler([self.queue.popleft()])
            n += 1
        return n


class UserEventRouter:
    """Reparte los eventos entre el carril HFT y el direccional (T30) de la misma cuenta."""

    def __init__(self, hft: Callable[[UserEvent], None] | None = None,
                 svc: ExecutionService | None = None,
                 external: Callable[[str], float] | None = None) -> None:
        """`external(símbolo)` = posición de otros carriles (HFT, arbitraje) en la cuenta: un
        evento de cuenta solo despierta a T30 si cambió SU parte (cada `sync` cuesta REST)."""
        self.hft, self.svc = hft, svc
        self.external = external or (lambda _s: 0.0)
        self.errors: list[str] = []

    def __call__(self, events: Iterable[UserEvent]) -> None:
        for ev in events:
            cid = ev.state.client_id if ev.state is not None else ""
            if self.hft is not None and (ev.kind != "order" or cid.startswith(HFT_PREFIX)):
                self.hft(ev)
            if self.svc is not None and ev.symbol and (
                    ev.kind == "account" or cid.startswith(CLIENT_PREFIX)):
                self._sync_t30(ev, cid)

    def _sync_t30(self, ev: UserEvent, cid: str) -> None:
        svc = self.svc
        assert svc is not None
        if ev.kind == "account" and ev.position is not None and abs(
                ev.position - self.external(ev.symbol) - svc.expected_qty(ev.symbol)) < 1e-12:
            return                                    # el cambio fue de otro carril
        for tr in svc.active(ev.symbol):
            if ev.kind == "account" or trade_key(cid) == tr.key:
                try:
                    svc.sync(tr)
                except BrokerError as e:              # la reconciliación lo resolverá
                    self.errors.append(f"{tr.key}: {e}")
                    hooks_service.service_error("execution.reconcile", e,
                                                detail={"via": "flujo de usuario"})
