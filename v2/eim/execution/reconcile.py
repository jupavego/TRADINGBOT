"""Reconciliación periódica entre el libro interno (`ExecutionService`) y el exchange.

En cada pasada, por símbolo:
1. Actualiza fills y cierres de las operaciones activas (`sync`).
2. Compara la posición esperada (suma de fills) con la del exchange → desvío relativo.
3. Toda posición abierta debe tener un SL vivo del lado que la cierra; si falta, se repone
   (o, sin operación conocida o sin poder reponerlo, se cierra a mercado).
4. Cancela órdenes `eim-` huérfanas (de operaciones cerradas/fallidas o desconocidas).
5. Desvío ≥ `kill_max_recon_drift` o sin respuesta del exchange ≥ `kill_max_disconnect_ms`
   → kill-switch; con el kill-switch activo se cierra todo de forma ordenada.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from eim.execution.broker import CLIENT_PREFIX, STOP, BrokerError, NetworkError, trade_key
from eim.execution.service import ExecutionService
from eim.risk.config import RiskConfig


@dataclass(frozen=True)
class SymbolRecon:
    symbol: str
    internal: float
    exchange: float
    drift: float
    protected: bool


@dataclass(frozen=True)
class ReconReport:
    t: int
    ok: bool
    symbols: tuple[SymbolRecon, ...]
    issues: tuple[str, ...]
    actions: tuple[str, ...]
    kill: tuple[str, ...]

    def to_json(self) -> dict:
        return asdict(self)


def drift_of(internal: float, exchange: float) -> float:
    big = max(abs(internal), abs(exchange))
    return 0.0 if big < 1e-12 else abs(exchange - internal) / big


class Reconciler:
    def __init__(self, svc: ExecutionService, cfg: RiskConfig) -> None:
        self.svc, self.cfg = svc, cfg
        self.last_contact: int | None = None
        self.last: ReconReport | None = None

    def run(self, symbols: tuple[str, ...], now: int) -> ReconReport:
        svc, b = self.svc, self.svc.broker
        rows: list[SymbolRecon] = []
        issues: list[str] = []
        actions: list[str] = []
        syms = tuple(dict.fromkeys((*symbols, *(t.symbol for t in svc.active()))))
        try:
            for tr in svc.active():
                svc.sync(tr)
            for s in syms:
                rows.append(self._symbol(s, issues, actions))
            self.last_contact = now
        except NetworkError as e:
            if self.last_contact is None:             # sin contacto previo: el corte empieza aquí
                self.last_contact = now
            gone = now - self.last_contact
            issues.append(f"sin respuesta del exchange: {e}")
            kill = svc.kill.check_rules(self.cfg, now, disconnected_ms=gone)
            return self._done(now, False, rows, issues, actions, kill)
        worst = max((r.drift for r in rows), default=0.0)
        kill = svc.kill.check_rules(self.cfg, now, recon_drift=worst)
        if svc.kill.close_requested:
            for s in syms:
                if svc.active(s) or b.position(s).qty:
                    try:
                        flat = svc.flatten(s, "kill-switch")
                    except BrokerError as e:
                        flat = False
                        issues.append(f"{s}: cierre fallido: {e}")
                    actions.append(f"{s}: cierre ordenado por kill-switch → "
                                   f"{'plano' if flat else 'pendiente'}")
        ok = not issues and not kill and all(r.drift == 0 for r in rows)
        return self._done(now, ok, rows, issues, actions, kill)

    def _done(self, now: int, ok: bool, rows: list[SymbolRecon], issues: list[str],
              actions: list[str], kill: list[str]) -> ReconReport:
        self.last = ReconReport(now, ok, tuple(rows), tuple(issues), tuple(actions), tuple(kill))
        return self.last

    def _symbol(self, s: str, issues: list[str], actions: list[str]) -> SymbolRecon:
        svc, b = self.svc, self.svc.broker
        pos = b.position(s).qty
        internal = svc.expected_qty(s)
        drift = drift_of(internal, pos)
        if drift > 0:                     # fills o SL entre lecturas: se relee antes de juzgar
            for tr in svc.active(s):
                svc.sync(tr)
            pos = b.position(s).qty
            internal = svc.expected_qty(s)
            drift = drift_of(internal, pos)
        if drift > 0:
            issues.append(f"{s}: posición interna {internal} ≠ exchange {pos}")
        orders = b.open_orders(s)
        protected = pos == 0 or any(o.kind == STOP and o.side * pos < 0 and
                                    (o.close_position or o.reduce_only) for o in orders)
        if not protected:
            issues.append(f"{s}: posición {pos} sin SL")
            trades = [t for t in svc.active(s) if t.side * pos > 0]
            if trades:
                svc.repair_sl(trades[0])
                actions.append(f"{s}: SL repuesto en {trades[0].sl}")
            else:
                flat = svc.flatten(s, "posición desconocida sin SL")
                actions.append(f"{s}: posición desconocida cerrada → "
                               f"{'plano' if flat else 'pendiente'}")
            protected = any(o.kind == STOP and o.side * pos < 0 for o in b.open_orders(s)) \
                or b.position(s).qty == 0
        live = {t.key for t in svc.active(s)}
        for o in orders:
            if o.client_id.startswith(CLIENT_PREFIX) and trade_key(o.client_id) not in live:
                b.cancel(s, o.client_id, o.conditional)
                actions.append(f"{s}: orden huérfana {o.client_id} cancelada")
        return SymbolRecon(s, internal, pos, drift, protected)
