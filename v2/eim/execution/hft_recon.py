"""Reconciliación continua del carril HFT (T83): libro del carril = exchange, o kill-switch.

Red de seguridad, no la vía de los fills (esa es el flujo de usuario). En cada pasada:
1. Consulta por id las órdenes vivas sin noticias hace `STALE_MS` (o todas si hay desvío): así
   se recuperan fills y cierres perdidos durante un corte del flujo de usuario.
2. Compara la posición del carril con la del exchange (menos `external`: lo que tengan el carril
   direccional o el arbitraje en el mismo símbolo). Si difieren tras releer → **divergencia** →
   kill-switch global y del carril (de `killswitch.py`; solo se apagan a mano).
3. Cancela las órdenes `eih-` abiertas en el exchange que el carril no tiene vivas (huérfanas,
   p. ej. de un proceso anterior).
4. Sin respuesta del exchange durante `recon_max_silence_ms` → kill-switch (misma regla).
Reutiliza `ReconReport`, `SymbolRecon` y `drift_of` de `reconcile.py`. Si el carril comparte
cuenta con T30, a su `Reconciler` hay que pasarle la posición HFT en `external` (y viceversa).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from eim.execution.broker import HFT_PREFIX, NetworkError, RateLimited
from eim.execution.hft_executor import HftExecutor
from eim.execution.reconcile import ReconReport, SymbolRecon, drift_of
from eim.observability import hooks_service
from eim.risk.hft_config import HftRiskConfig
from eim.risk.killswitch import KillSwitch

STALE_MS = 2_000
COMPONENT = "execution.hft"


class HftReconciler:
    def __init__(self, executor: HftExecutor, cfg: HftRiskConfig, kill: KillSwitch,
                 lane_kill: KillSwitch, external: Callable[[str], float] | None = None,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        self.ex, self.cfg, self.kill, self.lane_kill = executor, cfg, kill, lane_kill
        self.external = external or (lambda _s: 0.0)
        self._clock = clock
        self.last_contact: int | None = None
        self.last: ReconReport | None = None

    def _kill(self, reason: str, now: int) -> list[str]:
        for ks in (self.kill, self.lane_kill):
            ks.activate(reason, now, by="regla:hft_reconciliacion")
        return [reason]

    def _refresh(self, symbol: str, now: int, everything: bool) -> None:
        led, b = self.ex.ledger, self.ex.broker
        for o in led.live(symbol):
            if not everything and now - o.updated_at < STALE_MS:
                continue
            st = b.get_order(symbol, o.spec.client_id, False)
            if st is None:
                led.on_gone(o.spec.client_id)
            else:
                led.on_state(st)

    def _exchange_qty(self, symbol: str) -> float:
        return round(self.ex.broker.position(symbol).qty - self.external(symbol), 10)

    def run(self, symbol: str, now: int | None = None) -> ReconReport:
        now = self._clock() if now is None else now
        led, b, tol = self.ex.ledger, self.ex.broker, self.cfg.recon_qty_tolerance
        issues: list[str] = []
        actions: list[str] = []
        try:
            self._refresh(symbol, now, everything=False)
            exch, mine = self._exchange_qty(symbol), led.position(symbol)
            if abs(exch - mine) > tol:                # fills en vuelo: se relee antes de juzgar
                self._refresh(symbol, now, everything=True)
                exch, mine = self._exchange_qty(symbol), led.position(symbol)
            live = {o.spec.client_id for o in led.live(symbol)}
            for o in b.open_orders(symbol):
                if o.client_id.startswith(HFT_PREFIX) and o.client_id not in live:
                    b.cancel(symbol, o.client_id, False)
                    actions.append(f"{symbol}: orden huérfana {o.client_id} cancelada")
            self.last_contact = now
        except NetworkError as e:
            if isinstance(e, RateLimited):
                led.on_rate_limit(e)
            if self.last_contact is None:
                self.last_contact = now
            silent = now - self.last_contact
            issues.append(f"sin respuesta del exchange hace {silent / 1000:.0f} s: {e}")
            kill = self._kill(f"HFT: exchange sin respuesta {silent / 1000:.0f} s", now) \
                if silent >= self.cfg.recon_max_silence_ms else []
            return self._done(now, False, (), issues, actions, kill)
        kill: list[str] = []
        if abs(exch - mine) > tol:
            issues.append(f"{symbol}: posición del carril {mine:g} ≠ exchange {exch:g}")
            kill = self._kill(f"HFT: divergencia de posición {mine:g} ≠ {exch:g} en {symbol}", now)
        unknown = [o.spec.client_id for o in led.live(symbol) if o.status == "DESCONOCIDA"]
        if unknown:
            issues.append(f"{symbol}: {len(unknown)} órdenes en estado desconocido")
        row = SymbolRecon(symbol, mine, exch, drift_of(mine, exch), protected=not unknown)
        return self._done(now, not issues, (row,), issues, actions, kill)

    def _done(self, now: int, ok: bool, rows: tuple[SymbolRecon, ...], issues: list[str],
              actions: list[str], kill: list[str]) -> ReconReport:
        self.last = ReconReport(now, ok, rows, tuple(issues), tuple(actions), tuple(kill))
        hooks_service.beat(COMPONENT, status="ok" if ok else "degraded", mode=self.ex.mode,
                           detail={"issues": len(issues), "actions": len(actions),
                                   "kill_rules": len(kill)})
        return self.last
