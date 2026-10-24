"""Ejecutor del carril HFT (T83) sobre el `Broker` existente: post-only, reduce-only, sin reenvíos.

- `place_hft` solo lo llama `HftGateway` (tras `HftRiskEngine.verify_hft`) y envía exactamente
  la orden de la decisión: `GTX` (post-only) para cotizar, `IOC` para tomar, reduce-only para
  salir, a mercado solo para cerrar. Id de cliente determinista (`eih-…`, `hft_client_id`):
  reenviar la misma decisión devuelve la orden ya enviada, nunca otra (doble envío).
- Sin reenvío a ciegas: un resultado desconocido queda `DESCONOCIDA` (la orden pudo llegar) y lo
  resuelven el flujo de usuario o la reconciliación; un 429/418 deja al libro en espera
  (`rate_limited_until`) y no se consulta ni se reenvía nada mientras dure.
- Rechazos del exchange (post-only que cruzaría `-5022`, nocional mínimo `-4164`, reduce-only
  `-2022`…) quedan `RECHAZADA` con su motivo, sin reintento.
- `cancel` es idempotente (orden cerrada o ya pedida hace < `CANCEL_REPEAT_MS` → no hace nada);
  `cancel_all` cancela del lado cliente solo las órdenes `eih-` vivas del carril (nunca las de
  otro carril de la misma cuenta). La confirmación llega por evento.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from eim.execution.broker import (
    LIMIT,
    Broker,
    BrokerError,
    NetworkError,
    OrderRejected,
    OrderSpec,
    OrderState,
    RateLimited,
)
from eim.execution.hft_ledger import HftLedger
from eim.execution.service import ensure_order
from eim.risk.hft_models import HftDecision

CANCEL_REPEAT_MS = 500
REJECT_REASONS = {-5022: "post-only que casaría como taker", -4164: "nocional mínimo",
                  -2022: "reduce-only rechazada", -1111: "precisión de cantidad",
                  -4131: "precio fuera de la banda del mercado"}


class HftExecutor:
    def __init__(self, broker: Broker, ledger: HftLedger,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000),
                 backoff: float = 0.05, sleep: Callable[[float], None] = time.sleep) -> None:
        self.broker, self.ledger, self.mode = broker, ledger, broker.mode
        self.clock, self._backoff, self._sleep = clock, backoff, sleep
        self.rejections: list[tuple[str, int | None, str]] = []   # (id, código, motivo)

    @staticmethod
    def spec_of(d: HftDecision) -> OrderSpec:
        """La orden que autoriza la decisión, y ninguna otra."""
        o = d.order
        limit = o.kind == LIMIT
        return OrderSpec(d.client_id, o.symbol, o.side, o.kind, qty=o.qty,
                         price=o.price if limit else None, reduce_only=o.reduce_only,
                         tif=o.tif if limit else "GTC")

    def place_hft(self, d: HftDecision) -> OrderState | None:
        """Envía la orden de una decisión ya verificada. None si no quedó aceptada."""
        known = self.ledger.orders.get(d.client_id)
        if known is not None:                          # misma decisión reenviada: idempotente
            return known.state
        spec = self.spec_of(d)
        self.ledger.note_sent(spec, self.clock())
        try:
            st = ensure_order(self.broker, spec, retries=0, backoff=self._backoff,
                              sleep=self._sleep)
        except RateLimited as e:
            self.ledger.on_rate_limit(e)
            self.ledger.on_unknown(spec.client_id, str(e))
            return None
        except OrderRejected as e:
            why = REJECT_REASONS.get(e.code or 0, str(e))
            self.ledger.on_reject(spec.client_id, why)
            self.rejections.append((spec.client_id, e.code, why))
            return None
        except NetworkError as e:
            self.ledger.on_unknown(spec.client_id, str(e))
            return None
        self.ledger.on_state(st)
        return st

    def cancel(self, cid: str) -> bool:
        """Pide cancelar una orden del carril. False si no hacía falta o no se pudo."""
        o = self.ledger.orders.get(cid)
        now = self.clock()
        if o is None or not o.live or (o.cancel_at is not None
                                       and now - o.cancel_at < CANCEL_REPEAT_MS):
            return False
        self.ledger.note_cancel(cid, now)
        try:
            self.broker.cancel(o.spec.symbol, cid, False)
        except RateLimited as e:
            self.ledger.on_rate_limit(e)
            return False
        except BrokerError as e:
            o.error = f"cancelación fallida: {e}"[:200]
            return False
        return True

    def cancel_all(self, symbol: str) -> int:
        """Cancela del lado cliente todas las órdenes vivas del carril en `symbol`."""
        return sum(self.cancel(o.spec.client_id) for o in self.ledger.live(symbol))

    def arm_countdown(self, symbol: str, ms: int) -> bool:
        """Hombre muerto del exchange (`countdownCancelAll`, solo testnet): si el carril deja de
        renovarlo, Binance cancela TODAS las órdenes del símbolo al vencer. False si el bróker
        no lo tiene (simulado) o falló."""
        fn = getattr(self.broker, "countdown_cancel_all", None)
        if fn is None:
            return False
        try:
            fn(symbol, ms)
        except RateLimited as e:
            self.ledger.on_rate_limit(e)
            return False
        except BrokerError:
            return False
        return True
