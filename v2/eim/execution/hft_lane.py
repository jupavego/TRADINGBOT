"""Carril HFT (T83): riesgo + puerta + ejecutor + vigilancia, independiente de la estrategia.

Es el punto de entrada que usará el servicio en vivo (T85) y el que recorren las pruebas:
- `submit(orden, mercado, ahora)`: el motor decide (sellado) y, si aprueba, `HftGateway` envía.
  Ninguna otra ruta del carril envía órdenes: también el cierre por kill-switch pide decisión.
- `cancel(id)`: cancelación pedida por la estrategia (recotizar); respeta la tasa de
  cancelaciones. Las cancelaciones de emergencia (`tick`) no esperan a la tasa propia.
- `tick(mercado, ahora)`: vigilancia que corre con su propio temporizador. Con cualquier
  bloqueo (datos obsoletos, libro inconsistente, reloj desviado, flujo de usuario caído, sin
  latido de la estrategia = hombre muerto, kill-switch) → **cancelar todo** del lado cliente;
  con un kill-switch y posición → **cierre a mercado reduce-only** (con su decisión); un 418 →
  kill-switch del carril (solo se apaga a mano). Mientras todo está sano renueva el hombre
  muerto del exchange (`countdownCancelAll`, testnet): si el proceso muere, Binance cancela.
- `events`: registro de cada caída a estado seguro (también en el Observatorio).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from eim.execution.gateway import HftGateway
from eim.execution.hft_executor import HftExecutor
from eim.execution.hft_recon import COMPONENT, HftReconciler
from eim.execution.user_stream import UserEvent
from eim.observability import hooks_service
from eim.risk import hft_rules
from eim.risk.hft_engine import HftRiskEngine
from eim.risk.hft_models import SOURCE, HftDecision, HftMarket, HftOrder


@dataclass(frozen=True)
class LaneEvent:
    t: int
    kind: str                 # bloqueo | desbloqueo | cancelar_todo | cierre | kill | flujo | …
    detail: str


class HftLane:
    def __init__(self, engine: HftRiskEngine, executor: HftExecutor,
                 reconciler: HftReconciler | None = None) -> None:
        self.engine, self.ex, self.ledger = engine, executor, executor.ledger
        self.cfg = engine.config
        self.gateway = HftGateway(engine, executor)
        self.recon = reconciler or HftReconciler(executor, self.cfg, engine.kill_switch,
                                                 engine.lane_kill, clock=executor.clock)
        self.events: list[LaneEvent] = []
        self.decisions = 0
        self._blocked: tuple[str, ...] = ()
        self._countdown_at: int | None = None

    # --- registro ------------------------------------------------------------------
    def _log(self, now: int, kind: str, detail: str, status: str = "degraded") -> None:
        self.events.append(LaneEvent(now, kind, detail))
        hooks_service.service_event(COMPONENT, kind, status=status,
                                    detail={"detail": detail[:300], "mode": self.ex.mode.value})

    # --- entradas de la estrategia y del flujo de usuario ------------------------------
    def heartbeat(self, now: int) -> None:
        self.ledger.heartbeat_t = now

    def set_user_stream(self, ok: bool, now: int) -> None:
        if ok != self.ledger.user_stream_ok:
            self.ledger.user_stream_ok = ok
            self._log(now, "flujo", "flujo de usuario " + ("reconectado" if ok else "caído"),
                      "ok" if ok else "degraded")

    def on_user_events(self, events: Iterable[UserEvent]) -> None:
        for ev in events:
            self.ledger.on_event(ev)

    def submit(self, order: HftOrder, market: HftMarket, now: int) -> HftDecision:
        acct = self.ledger.account(order.symbol, market.mid, now)
        d = self.engine.evaluate(order, market, acct, now)
        self.decisions += 1
        if d.approved:
            self.gateway.submit(d, now)
        return d

    def cancel(self, cid: str, market: HftMarket, now: int) -> bool:
        acct = self.ledger.account(market.symbol, market.mid, now)
        if not hft_rules.cancel_rate_ok(acct, self.cfg):
            self._log(now, "tasa", f"cancelación de {cid} aplazada: {acct.cancels_10s}/10 s, "
                      f"{acct.cancels_60s}/min")
            return False
        return self.ex.cancel(cid)

    # --- vigilancia independiente -------------------------------------------------------
    def tick(self, market: HftMarket, now: int) -> list[str]:
        sym, actions = market.symbol, []
        acct = self.ledger.account(sym, market.mid, now)
        if acct.banned and not self.engine.lane_kill.active:
            self.engine.lane_kill.activate("IP bloqueada por el exchange (418)", now,
                                           by="regla:hft_418")
            self._log(now, "kill", "418: kill-switch del carril (solo se apaga a mano)")
        bad = self.engine.blockers(market, acct, now)
        names = tuple(c.rule for c in bad)
        if names != self._blocked:
            self._blocked = names
            self._log(now, "bloqueo" if bad else "desbloqueo",
                      "; ".join(f"{c.rule}: {c.detail}" for c in bad) or "sin bloqueos",
                      "degraded" if bad else "ok")
        if bad and self.ledger.live(sym) and (n := self.ex.cancel_all(sym)):
            actions.append(f"cancelar todo: {n} órdenes ({', '.join(names)})")
            self._log(now, "cancelar_todo", actions[-1])
        if (self.engine.kill_switch.active or self.engine.lane_kill.active) and \
                self.ledger.position(sym) and not any(
                    o.spec.reduce_only and o.cancel_at is None for o in self.ledger.live(sym)):
            actions.append(self._flatten(market, now))
        if self.cfg.exchange_countdown_ms and not bad and (
                self._countdown_at is None
                or now - self._countdown_at >= self.cfg.exchange_countdown_ms // 3):
            if self.ex.arm_countdown(sym, self.cfg.exchange_countdown_ms):
                self._countdown_at = now
        return actions

    def _flatten(self, market: HftMarket, now: int) -> str:
        """Cierre ordenado del inventario: reduce-only a mercado, con su decisión sellada."""
        sym, pos = market.symbol, self.ledger.position(market.symbol)
        o = HftOrder(order_id=f"flatten-{sym}-{now}", source=SOURCE,
                     source_version=f"hft_lane@{self.cfg.version}", symbol=sym,
                     side=-1 if pos > 0 else 1, qty=abs(pos), kind="MARKET", reduce_only=True,
                     purpose="flatten", mode=self.ex.mode, asof=now,
                     expires_at=now + self.cfg.decision_ttl_ms)
        d = self.submit(o, market, now)
        what = (f"cierre de {pos:g} {sym} a mercado (reduce-only): "
                + ("enviado" if d.approved else f"vetado ({'; '.join(d.reasons)})"))
        self._log(now, "cierre", what)
        return what
