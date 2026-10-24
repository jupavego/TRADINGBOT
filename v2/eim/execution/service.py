"""Servicio de ejecución: convierte una orden aprobada en SL + TP + entrada y lleva el libro.

Orden de envío (lo que garantiza que «cortar la red a mitad no deja posición sin SL»):
1. SL y TP como órdenes condicionales `close_position` (solo reducen; cubren cualquier
   cantidad llenada, también fills parciales). Si alguna falla, no se envía la entrada.
2. Entrada MARKET o LIMIT. Si el resultado es desconocido, la posición que pudiera existir ya
   está protegida y la reconciliación resuelve el estado.

Idempotencia: cada orden lleva un id de cliente determinista. Ante un error de red se consulta
la orden por ese id; solo si el exchange confirma que no existe se reenvía (nunca a ciegas).
`place` solo lo llama `OrderGateway` (verificado estáticamente en tests/risk/test_gate.py).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from eim.execution.broker import (
    CANCELED,
    EXPIRED,
    LIMIT,
    MARKET,
    REJECTED,
    STOP,
    TAKE_PROFIT,
    TRIGGERED,
    Broker,
    BrokerError,
    NetworkError,
    OrderRejected,
    OrderSpec,
    OrderState,
    RateLimited,
    client_id,
    trade_key,
)
from eim.execution.gateway import OrderIntent
from eim.observability import hooks
from eim.risk.killswitch import KillSwitch

PENDING, OPEN, CLOSED, FAILED = "PENDIENTE", "ABIERTA", "CERRADA", "FALLIDA"
ACTIVE = (PENDING, OPEN)


@dataclass
class LiveTrade:
    key: str
    plan_id: str
    symbol: str
    side: int
    qty: float
    leverage: int
    sl: float
    tp: float | None
    entry_kind: str
    status: str = PENDING
    filled: float = 0.0
    avg_entry: float | None = None
    exit_reason: str = ""
    sl_role: str = "s"                     # cambia al reparar el SL (s2, s3…)
    closes: int = 0
    opened_at: int | None = None           # ms del primer fill
    closed_at: int | None = None
    exit_price: float | None = None        # precio medio de salida (None si se desconoce)
    events: list[str] = field(default_factory=list)

    def cid(self, role: str) -> str:
        return f"{self.key}-{role}"

    def to_json(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @property
    def pnl(self) -> float | None:
        """Resultado bruto (sin comisiones ni funding) de una operación cerrada."""
        if self.exit_price is None or self.avg_entry is None:
            return None
        return (self.exit_price - self.avg_entry) * self.side * self.filled

    @property
    def r(self) -> float | None:
        """Resultado bruto en R (riesgo inicial = |entrada − SL|)."""
        risk = abs((self.avg_entry or 0.0) - self.sl) * self.filled
        return None if self.pnl is None or risk <= 0 else self.pnl / risk


def ensure_order(broker: Broker, spec: OrderSpec, retries: int = 3, backoff: float = 0.5,
                 sleep: Callable[[float], None] = time.sleep) -> OrderState:
    """Envía con reintentos seguros: reenvía solo si el exchange confirma que no existe.

    Único punto que entrega órdenes a un broker (también las patas de arbitraje, T45)."""
    for attempt in range(retries + 1):
        try:
            return broker.post_order(spec)
        except OrderRejected as e:
            if not e.duplicate:
                raise
        except RateLimited:
            raise                                 # T83: ni consultar ni reenviar en la espera
        except NetworkError:
            pass
        for q in range(retries + 1):              # consulta hasta tener respuesta firme
            sleep(backoff * 2 ** min(attempt + q, 5))
            try:
                found = broker.get_order(spec.symbol, spec.client_id, spec.conditional)
            except NetworkError:
                continue
            if found is not None:
                return found
            break                                 # no existe: se puede reenviar
        else:
            break                                 # sin respuesta firme: no reenviar
    raise NetworkError(f"orden {spec.client_id} en estado desconocido tras reintentos")


class ExecutionError(BrokerError):
    pass


class ExecutionService:
    def __init__(self, broker: Broker, kill: KillSwitch, retries: int = 3,
                 backoff: float = 0.5, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        self.broker, self.kill, self.mode = broker, kill, broker.mode
        self._retries, self._backoff, self._sleep, self._clock = retries, backoff, sleep, clock
        self.trades: dict[str, LiveTrade] = {}

    # --- utilidades --------------------------------------------------------
    def _log(self, tr: LiveTrade, msg: str) -> None:
        tr.events.append(f"{self._clock()} {msg}")

    def active(self, symbol: str | None = None) -> list[LiveTrade]:
        return [t for t in self.trades.values()
                if t.status in ACTIVE and (symbol is None or t.symbol == symbol)]

    def expected_qty(self, symbol: str) -> float:
        return round(sum(t.side * t.filled for t in self.active(symbol)), 10)

    def _ensure(self, spec: OrderSpec) -> OrderState:
        return ensure_order(self.broker, spec, self._retries, self._backoff, self._sleep)

    def _cancel_quiet(self, tr: LiveTrade, role: str, conditional: bool) -> None:
        try:
            self.broker.cancel(tr.symbol, tr.cid(role), conditional)
        except BrokerError as e:
            self._log(tr, f"no se pudo cancelar {role}: {e}")

    def _cancel_protection(self, tr: LiveTrade) -> None:
        for role in {tr.sl_role, "s"}:
            self._cancel_quiet(tr, role, True)
        if tr.tp is not None:
            self._cancel_quiet(tr, "t", True)

    # --- apertura (solo desde OrderGateway) ---------------------------------
    def place(self, order: OrderIntent) -> str:
        key = trade_key(client_id(order.plan_id, order.symbol, "e"))
        if key in self.trades:
            old = self.trades[key]
            if old.status == FAILED:
                raise ExecutionError(f"este plan ya falló ({old.exit_reason}); "
                                     "hace falta un plan nuevo")
            return key                                # misma decisión reenviada: idempotente
        if self.kill.active:
            raise PermissionError("kill-switch activo: no se abren posiciones")
        if order.mode != self.mode:
            raise PermissionError(f"orden en modo {order.mode.value} y broker en {self.mode.value}")
        b, s = self.broker, order.symbol
        qty = b.round_qty(s, order.size)
        if qty <= 0:
            raise OrderRejected(f"tamaño {order.size} por debajo del mínimo de {s}")
        tr = LiveTrade(key=key, plan_id=order.plan_id, symbol=s, side=order.side, qty=qty,
                       leverage=int(order.leverage), sl=b.round_price(s, order.sl),
                       tp=b.round_price(s, order.tp[0]) if order.tp else None,
                       entry_kind=order.entry_kind)
        self.trades[key] = tr
        try:
            b.prepare(s, tr.leverage)
            self._ensure(OrderSpec(tr.cid("s"), s, -tr.side, STOP, trigger=tr.sl,
                                   close_position=True))
            if tr.tp is not None:
                self._ensure(OrderSpec(tr.cid("t"), s, -tr.side, TAKE_PROFIT, trigger=tr.tp,
                                       close_position=True))
        except BrokerError as e:
            self._fail(tr, f"protección no colocada: {e}")
            raise ExecutionError(f"sin SL/TP no se entra: {e}") from e
        self._log(tr, f"SL {tr.sl} y TP {tr.tp} colocados")
        entry = OrderSpec(tr.cid("e"), s, tr.side, order.entry_kind, qty=qty,
                          price=b.round_price(s, order.entry) if order.entry_kind == LIMIT
                          else None)
        try:
            st = self._ensure(entry)
        except OrderRejected as e:
            self._fail(tr, f"entrada rechazada: {e}")
            raise ExecutionError(f"entrada rechazada: {e}") from e
        except NetworkError as e:
            self._log(tr, f"entrada en estado desconocido ({e}); la reconciliación lo resuelve")
            return key
        self._apply_entry(tr, st)
        return key

    def _fail(self, tr: LiveTrade, why: str) -> None:
        self._cancel_protection(tr)
        tr.status, tr.exit_reason = FAILED, why
        self._log(tr, why)

    def _apply_entry(self, tr: LiveTrade, st: OrderState) -> None:
        if st.filled > tr.filled:
            self._log(tr, f"entrada llenada {st.filled}/{tr.qty} a {st.avg_price}")
            hooks.fill_event(tr.plan_id, self.mode, tr.key, "entrada", st.filled - tr.filled,
                             st.avg_price)
        tr.filled, tr.avg_entry = st.filled, st.avg_price or tr.avg_entry
        if tr.filled > 0 and tr.status == PENDING:
            tr.status, tr.opened_at = OPEN, self._clock()
        elif tr.filled == 0 and st.status in (CANCELED, EXPIRED, REJECTED):
            self._fail(tr, f"entrada {st.status} sin llenar")

    # --- seguimiento -------------------------------------------------------
    def sync(self, tr: LiveTrade) -> None:
        """Actualiza fills y detecta el cierre por SL/TP. Lanza `NetworkError` sin red."""
        if tr.status not in ACTIVE:
            return
        b = self.broker
        st = b.get_order(tr.symbol, tr.cid("e"), False)
        if st is None:
            if tr.status == PENDING and tr.filled == 0:
                self._fail(tr, "la entrada nunca llegó al exchange")
            return
        self._apply_entry(tr, st)
        if tr.status != OPEN:
            return
        pos = b.position(tr.symbol).qty
        fired = [(r, o) for r, cond in ((tr.sl_role, True), ("t", True))
                 if (o := b.get_order(tr.symbol, tr.cid(r), cond)) is not None
                 and o.status == TRIGGERED]
        hit = [r for r, _ in fired]
        if hit or pos * tr.side <= 0:
            if st.is_open:
                self._cancel_quiet(tr, "e", False)
            self._cancel_protection(tr)
            tr.status, tr.closed_at = CLOSED, self._clock()
            tr.exit_reason = ("TP" if hit == ["t"] else "SL") if hit else "posición cerrada fuera"
            tr.exit_price = fired[0][1].avg_price if fired else None
            self._log(tr, f"cerrada: {tr.exit_reason}")
            hooks.fill_event(tr.plan_id, self.mode, tr.key, tr.exit_reason, tr.filled,
                             tr.exit_price)

    def repair_sl(self, tr: LiveTrade) -> None:
        """Repone el SL de una posición desprotegida; si ya se cruzó, cierra a mercado."""
        n = int(tr.sl_role[1:] or 1) + 1
        tr.sl_role = f"s{n}"
        try:
            self._ensure(OrderSpec(tr.cid(tr.sl_role), tr.symbol, -tr.side, STOP,
                                   trigger=tr.sl, close_position=True))
            self._log(tr, f"SL repuesto ({tr.sl_role})")
        except OrderRejected as e:
            self._log(tr, f"SL no reponible ({e}): cierre a mercado")
            self.flatten(tr.symbol, "SL no reponible")

    def flatten(self, symbol: str, reason: str, keep: float = 0.0) -> bool:
        """Cierre ordenado: cancela entradas, cierra a mercado (reduce-only) y luego quita SL/TP.

        El SL se retira solo cuando la posición ya es 0. Devuelve True si quedó plano.
        `keep` = parte de la posición que no es del carril direccional (la pata de futuros de
        un arbitraje abierto, T45): no se cierra aquí (la cierra su ejecutor, con su pata spot).
        """
        b = self.broker
        trades = self.active(symbol)
        for tr in trades:
            self._cancel_quiet(tr, "e", False)
        qty = round(b.position(symbol).qty - keep, 10)
        if qty:
            tag = trades[0] if trades else None
            n = (tag.closes + 1) if tag else 1
            if tag:
                tag.closes = n
            cid = tag.cid(f"x{n}") if tag else client_id(f"flat:{self._clock()}", symbol, "x")
            done = self._ensure(OrderSpec(cid, symbol, -1 if qty > 0 else 1, MARKET,
                                          qty=abs(qty), reduce_only=True))
            exit_px = done.avg_price
        else:
            exit_px = None
        flat = abs(b.position(symbol).qty - keep) < 1e-12
        for tr in trades:
            if flat:
                self._cancel_protection(tr)
                tr.status, tr.exit_reason = CLOSED, f"cierre ordenado: {reason}"
                tr.closed_at = self._clock()
                tr.exit_price = exit_px if tr.filled else None
                self._log(tr, tr.exit_reason)
                hooks.fill_event(tr.plan_id, self.mode, tr.key, tr.exit_reason, tr.filled,
                                 tr.exit_price)
        return flat
