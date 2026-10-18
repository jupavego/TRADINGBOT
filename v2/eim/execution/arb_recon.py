"""Reconciliación de los arbitrajes con el exchange (T45). En cada pasada:

1. Órdenes sin estado firme (`ENVIANDO`, `DESCONOCIDO`, abiertas): se consultan por su id; las
   abiertas se cancelan (su tiempo límite ya pasó) y lo llenado se aplica por diferencia.
2. Libro vs exchange: los futuros del símbolo (menos lo del carril direccional) y el saldo spot
   (menos el saldo ajeno de referencia) deben coincidir con las patas; si el exchange tiene
   menos (liquidación, cierre externo), se adopta lo que hay.
3. Descubierto (una pata sin su cobertura): se recorta la pata que sobra o, si es polvo de
   futuros, se completa la otra. Así no queda ninguna posición huérfana tras cortar la red.
4. Seguimiento: marca, margen aislado, distancia a liquidación y funding realmente cobrado
   frente al esperado por el plan.
Sin respuesta del exchange ≥ `kill_max_disconnect_ms` → kill-switch compartido; con el
kill-switch activo, cierre urgente de todos los arbitrajes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass

from eim.arbitrage.live.manage import settlements_between
from eim.execution.arb_book import (
    ACTIVE,
    CLOSED,
    FAILED,
    GONE,
    OPEN,
    PENDING,
    SENDING,
    UNHEDGED,
    UNKNOWN,
    UNSETTLED,
    ArbPosition,
)
from eim.execution.arb_executor import ArbExecutor
from eim.execution.arb_legs import LegOrder
from eim.execution.broker import BrokerError, NetworkError
from eim.risk.arb_config import ArbRiskConfig


@dataclass(frozen=True)
class ArbRecon:
    t: int
    ok: bool
    connected: bool
    issues: tuple[str, ...]
    actions: tuple[str, ...]

    def to_json(self) -> dict:
        return asdict(self)


class ArbReconciler:
    def __init__(self, ex: ArbExecutor, cfg: ArbRiskConfig,
                 directional: Callable[[str], float] = lambda _s: 0.0) -> None:
        self.ex, self.cfg, self.directional = ex, cfg, directional
        self.last_contact: int | None = None
        self.last: ArbRecon | None = None

    def run(self, now: int) -> ArbRecon:
        ex = self.ex
        issues: list[str] = []
        actions: list[str] = []
        try:
            for pos in ex.active():
                self._settle(pos, actions)
            self._exchange(issues, actions)
            for pos in ex.active():
                self._fix(pos, issues, actions)
            for pos in ex.active():
                self._track(pos, now)
            self.last_contact = now
        except NetworkError as e:
            if self.last_contact is None:
                self.last_contact = now
            gone = now - self.last_contact
            issues.append(f"sin respuesta del exchange: {e}")
            if gone >= self.cfg.kill_max_disconnect_ms:
                ex.kill.activate(f"arbitraje: desconectado {gone / 1000:.0f} s ≥ "
                                 f"{self.cfg.kill_max_disconnect_ms / 1000:.0f} s", now,
                                 by="regla:desconexion")
            ex.persist()
            return self._done(now, False, False, issues, actions)
        if ex.kill.active and ex.active():
            flat = ex.flatten_all("kill-switch")
            actions.append(f"kill-switch: cierre urgente → {'plano' if flat else 'pendiente'}")
        ex.persist()
        ok = not issues and all(p.status != UNHEDGED for p in ex.active())
        return self._done(now, ok, True, issues, actions)

    def _done(self, now: int, ok: bool, connected: bool, issues: list[str],
              actions: list[str]) -> ArbRecon:
        self.last = ArbRecon(now, ok, connected, tuple(issues), tuple(actions))
        return self.last

    # --- 1. órdenes sin estado firme -------------------------------------------
    def _settle(self, pos: ArbPosition, actions: list[str]) -> None:
        ex = self.ex
        for rec in pos.orders:
            if rec.status not in UNSETTLED:
                continue
            b = ex.spot if rec.market == "spot" else ex.fut
            st = b.get_order(rec.symbol, rec.cid, False)
            if st is not None and st.is_open:
                b.cancel(rec.symbol, rec.cid, False)
                st = b.get_order(rec.symbol, rec.cid, False) or st
            if st is None:
                if rec.status in (SENDING, UNKNOWN):
                    rec.status = GONE
                    actions.append(f"{pos.key}: orden {rec.cid} nunca llegó al exchange")
                continue
            moved = pos.apply(rec, st, ex.legs.base(rec.market, rec.symbol))
            if moved:
                actions.append(f"{pos.key}: {rec.cid} resuelta ({st.status}, {moved:+.6g})")
        if pos.status in (PENDING, UNHEDGED) and not any(r.status in UNSETTLED
                                                         for r in pos.orders):
            if pos.hedged > 0 and not ex.material(pos):
                pos.status = OPEN
                pos.opened_at = pos.opened_at or ex.now()
                actions.append(f"{pos.key}: cubierta tras resolver sus órdenes")

    # --- 2. libro vs exchange ------------------------------------------------------
    def _exchange(self, issues: list[str], actions: list[str]) -> None:
        ex = self.ex
        act = ex.active()
        for sym in sorted({p.fut.symbol for p in act}):
            pos = [p for p in act if p.fut.symbol == sym]
            real = round(ex.fut.position(sym).qty - self.directional(sym), 12)
            book = round(sum(p.fut.held for p in pos), 12)
            if abs(real - book) > 1e-12 and len(pos) == 1 and not self._pending(pos[0]):
                issues.append(f"{sym}: futuros del exchange {real:+.6g} ≠ libro {book:+.6g}")
                pos[0].fut.held = real
                actions.append(f"{pos[0].key}: se adopta la posición de futuros del exchange "
                               "(liquidación o cierre externo)")
        for asset in sorted({p.asset for p in act}):
            pos = [p for p in act if p.asset == asset]
            bal = ex.spot.position(pos[0].spot.symbol).qty
            held = sum(p.spot.held for p in pos)
            want = ex.spot_baseline.get(asset, 0.0) + held
            short = round(want - bal, 12)
            if short > ex.p.hedge_tol * max(held, 1e-12) and not any(map(self._pending, pos)):
                issues.append(f"{asset}: saldo spot {bal:.8g} < esperado {want:.8g}")
                for p in pos:
                    take = min(short, max(p.spot.held, 0.0))
                    p.spot.held, short = round(p.spot.held - take, 12), short - take
                actions.append(f"{asset}: se adopta el saldo spot del exchange")
        for asset in {p.asset for p in ex.positions.values()} - {p.asset for p in act}:
            sym = next(p.spot.symbol for p in ex.positions.values() if p.asset == asset)
            ex.spot_baseline[asset] = ex.spot.position(sym).qty    # sin arbitrajes: referencia

    @staticmethod
    def _pending(pos: ArbPosition) -> bool:
        return any(r.status in UNSETTLED for r in pos.orders)

    # --- 3. descubiertos -----------------------------------------------------------
    def _fix(self, pos: ArbPosition, issues: list[str], actions: list[str]) -> None:
        ex = self.ex
        if self._pending(pos):
            return
        if not ex.material(pos):
            if pos.flat or pos.hedged <= 0:
                ex.finish(pos, CLOSED if pos.opened_at else FAILED,
                           pos.exit_reason or "sin posición tras la reconciliación")
            elif pos.status == UNHEDGED:
                pos.status = OPEN
                pos.opened_at = pos.opened_at or ex.now()
            return
        res = pos.residual
        issues.append(f"{pos.key}: descubierto {res:+.6g} {pos.asset}")
        s, f = pos.spot, pos.fut
        if res > 0:                                       # sobra spot: se vende
            o = LegOrder("spot", s.symbol, -1, ex.spot.round_qty(s.symbol, res))
        elif ex.fut.round_qty(f.symbol, -res) > 0:        # sobra corto: se recompra
            o = LegOrder("usdm", f.symbol, 1, ex.fut.round_qty(f.symbol, -res), reduce_only=True)
        else:                                             # polvo de futuros: se completa spot
            o = LegOrder("spot", s.symbol, 1, ex.spot.round_qty(s.symbol, -res))
        try:
            moved = ex.legs.trim(pos, o, "recortar", force=True)
        except BrokerError as e:
            issues.append(f"{pos.key}: no se pudo corregir el descubierto: {e}")
            pos.status = UNHEDGED
            return
        actions.append(f"{pos.key}: descubierto corregido en {o.symbol} ({o.side * moved:+.6g})")
        if pos.hedged <= 0 and not ex.material(pos):
            ex.finish(pos, CLOSED if pos.opened_at else FAILED,
                       "pata incompleta deshecha en la reconciliación: posición neta cero")
        else:
            pos.status = UNHEDGED if ex.material(pos) else OPEN
            if pos.status == OPEN:
                pos.opened_at = pos.opened_at or ex.now()

    # --- 4. seguimiento ------------------------------------------------------------
    def _track(self, pos: ArbPosition, now: int) -> None:
        if pos.status not in ACTIVE or pos.opened_at is None or not pos.fut.held:
            return
        ex = self.ex
        r = ex.fut.position_risk(pos.fut.symbol)
        mark, liq = r.get("mark"), r.get("liq")
        pos.mark, pos.liq_price = mark, liq
        if r.get("margin") is not None:
            pos.margin_equity = float(r["margin"] or 0.0) + float(r.get("upnl") or 0.0)
        pos.liq_move = abs(liq - mark) / mark if liq and mark else None
        top = ex.spot.book_top(pos.spot.symbol)
        pos.spot_px = (top[0] + top[1]) / 2 if top else pos.spot_px
        rows = ex.fut.funding_income(pos.fut.symbol, pos.opened_at)
        pos.funding_received = round(sum(a for _, a in rows), 8)
        pos.funding_n = len(rows)
        rate, interval = pos.plan.get("funding_rate"), pos.plan.get("interval_h")
        if rate is not None and interval and mark:
            n = settlements_between(pos.opened_at, now, float(interval))
            pos.funding_expected = round(rate * pos.hedged * mark * n, 8)
