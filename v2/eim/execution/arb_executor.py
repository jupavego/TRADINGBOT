"""Ejecutor de arbitraje en testnet (T45): spot testnet + futuros USDⓈ-M testnet.

- `place_arb` (solo desde `ArbGateway`, tras verificar la `ArbDecision`): idempotente por
  `arb_id`; comprueba cantidades mínimas, libros y que el precio de la testnet no se aparte del
  de referencia; prepara el futuro (aislado, apalancamiento) y abre las dos patas con `Legs.pair`
  (la menos líquida primero según la profundidad de la testnet). Una pata incompleta se deshace:
  la posición queda cubierta o neta en cero.
- `close` / `rebalance` / `flatten_all`: el mismo motor de dos patas. Un cierre no urgente cuya
  segunda pata falla rehace la primera (sigue cubierto y se reintenta); uno urgente (kill-switch,
  liquidación) termina a mercado.
- Pérdida al deshacer sobre el tope de la decisión → kill-switch compartido (`regla:pata`).
Modo = el de los brokers: TESTNET (Binance testnet) o SIMULADO (`arb_sim`, exchange en memoria
del bróker simulado). Nunca REAL: con brokers de otro modo no se construye.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any

from eim.arbitrage.live.manage import Action
from eim.core import Mode
from eim.execution.arb_book import (
    ACTIVE,
    CLOSED,
    CLOSING,
    FAILED,
    OPEN,
    UNHEDGED,
    UNSETTLED,
    ArbLeg,
    ArbPosition,
)
from eim.execution.arb_legs import ExecParams, LegOrder, Legs, LegUnknown, PairResult
from eim.execution.broker import BrokerError
from eim.execution.service import ExecutionError
from eim.risk.arb_models import ArbDecision
from eim.risk.killswitch import KillSwitch


class ArbExecutor:
    def __init__(self, spot: Any, fut: Any, kill: KillSwitch, params: ExecParams | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000),
                 save: Callable[[dict], None] = lambda _d: None,
                 journal: Callable[[str, dict], None] = lambda _k, _d: None) -> None:
        if spot.mode != fut.mode or spot.mode not in (Mode.TESTNET, Mode.SIMULADO):
            raise PermissionError("el arbitraje solo se ejecuta en TESTNET o SIMULADO")
        self.mode: Mode = spot.mode
        self.spot, self.fut, self.kill = spot, fut, kill
        self.p = params or ExecParams()
        self._clock, self._save, self.journal = clock, save, journal
        self.positions: dict[str, ArbPosition] = {}
        self.spot_baseline: dict[str, float] = {}       # saldo spot ajeno a los arbitrajes
        self.day: tuple[int, float] | None = None       # (inicio del día UTC, capital)
        self.legs = Legs({"spot": spot, "usdm": fut}, self.p, sleep, clock, self.persist)

    # --- estado --------------------------------------------------------------
    def dump(self) -> dict:
        return {"positions": [p.to_json() for p in self.positions.values()],
                "spot_baseline": self.spot_baseline, "day": self.day}

    def load(self, d: dict) -> None:
        self.positions = {x["key"]: ArbPosition.from_json(x) for x in d.get("positions", [])}
        self.spot_baseline = {k: float(v) for k, v in d.get("spot_baseline", {}).items()}
        day = d.get("day")
        self.day = (int(day[0]), float(day[1])) if day else None

    def persist(self) -> None:
        self._save(self.dump())

    def now(self) -> int:
        return self._clock()

    def active(self) -> list[ArbPosition]:
        return [p for p in self.positions.values() if p.status in ACTIVE]

    def open_keys(self) -> set[str]:
        return {f"{p.strategy}:{p.asset}" for p in self.active()}

    def futures_qty(self, symbol: str) -> float:
        """Futuros de arbitrajes activos en `symbol` (la reconciliación T30 los respeta)."""
        return round(sum(p.fut.held for p in self.active() if p.fut.symbol == symbol), 12)

    def _log(self, pos: ArbPosition, msg: str, kind: str = "evento") -> None:
        pos.events.append(f"{self._clock()} {msg}")
        self.journal(kind, {"key": pos.key, "arb": pos.arb_id, "msg": msg, "status": pos.status})

    # --- apertura (solo desde ArbGateway) --------------------------------------
    def place_arb(self, d: ArbDecision) -> str:
        plan = d.plan
        key = ArbPosition.key_of(plan.arb_id, plan.futures.symbol)
        if key in self.positions:
            old = self.positions[key]
            if old.status == FAILED:
                raise ExecutionError(f"este arbitraje ya falló ({old.exit_reason})")
            return key                                  # misma decisión reenviada
        if self.kill.active:
            raise PermissionError("kill-switch activo: no se abren arbitrajes")
        if d.mode != self.mode:
            raise PermissionError(f"decisión en modo {d.mode.value}: el ejecutor es "
                                  f"{self.mode.value}")
        sp, fp = plan.spot, plan.futures
        now = self._clock()
        pos = ArbPosition(
            key=key, arb_id=plan.arb_id, strategy=plan.strategy, variant=plan.variant,
            asset=plan.asset, leverage=d.leverage,
            legs={"spot": ArbLeg("spot", sp.symbol, sp.side),
                  "usdm": ArbLeg("usdm", fp.symbol, fp.side)},
            order=[lg.market for lg in plan.legs], plan=plan.model_dump(mode="json"),
            approved_qty=d.qty, max_leg_loss=d.max_leg_loss,
            max_leg_loss_bps=d.max_leg_loss_bps, created_at=now)
        self.positions[key] = pos
        self._log(pos, f"apertura aprobada: {d.qty:.6g} {plan.asset} ({plan.variant})", "orden")
        try:
            qty = self._precheck(pos, d.qty)
            self.fut.prepare(fp.symbol, d.leverage)
            if not [p for p in self.active() if p is not pos and p.asset == pos.asset]:
                self.spot_baseline[pos.asset] = self.spot.position(sp.symbol).qty
            first, second = self.legs.ordered(pos, qty, opening=True)
            r = self.legs.pair(pos, first, second, d.max_leg_loss_bps, urgent=False)
        except LegUnknown as e:
            pos.status = UNHEDGED
            self._log(pos, f"estado desconocido a mitad de la apertura ({e}); la reconciliación "
                      "lo resuelve")
            self.persist()
            return key
        except BrokerError as e:
            if not pos.orders or (pos.flat and not self._sent_unsettled(pos)):
                self.finish(pos, FAILED, f"no se abrió: {e}")
            else:                                       # algo se envió: lo resuelve la recon.
                pos.status = UNHEDGED
                self._log(pos, f"apertura interrumpida tras enviar órdenes ({e}); la "
                          "reconciliación lo resuelve")
                self.persist()
            return key
        self._after(pos, r, opening=True)
        return key

    @staticmethod
    def _sent_unsettled(pos: ArbPosition) -> bool:
        return any(o.status in UNSETTLED for o in pos.orders)

    def _precheck(self, pos: ArbPosition, qty: float) -> float:
        s, f = pos.spot.symbol, pos.fut.symbol
        q = self.fut.round_qty(f, self.spot.round_qty(s, qty))
        bid_s, bid_f = self.legs.top("spot", s)[0], self.legs.top("usdm", f)[0]
        if (q <= 0 or q * bid_s < self.spot.min_notional(s)
                or q * bid_f < self.p.min_futures_notional):
            raise BrokerError(f"cantidad {qty:.6g} bajo el mínimo de orden tras redondear ({q:g})")
        for lg in pos.plan["legs"]:
            bid, ask = self.legs.top(lg["market"], lg["symbol"])
            dev = abs((bid + ask) / 2 / lg["ref_price"] - 1)
            if dev > self.p.max_venue_dev:
                raise BrokerError(f"precio de testnet de {lg['symbol']} se aparta {dev:.1%} del "
                                  f"de referencia (máx. {self.p.max_venue_dev:.0%})")
        return q

    def _after(self, pos: ArbPosition, r: PairResult, opening: bool) -> None:
        for msg in r.issues:
            self._log(pos, msg)
        if r.reversed:
            pos.incident_loss += r.loss
            self._log(pos, f"pata incompleta: deshechos {r.reversed:.6g} ({r.loss:+.2f} USD; "
                      f"tope {pos.max_leg_loss_bps:g} pb)", "pata_incompleta")
        if r.over_cap:
            self.kill.activate(f"pata incompleta de {pos.key}: pérdida {r.loss:.2f} USD sobre "
                               f"el tope de {pos.max_leg_loss_bps:g} pb", self._clock(),
                               by="regla:pata")
        if self.material(pos):
            pos.status = UNHEDGED
            self._log(pos, f"descubierto {pos.residual:+.6g} {pos.asset}: la reconciliación "
                      "lo corrige")
        elif pos.hedged <= 0:
            self.finish(pos, FAILED if opening else CLOSED, (
                "pata incompleta deshecha: posición neta cero" if r.reversed else
                "; ".join(r.issues) or "sin llenar") if opening else pos.exit_reason)
            return
        elif opening:
            pos.status, pos.opened_at = OPEN, self._clock()
            self._log(pos, f"abierta: spot {pos.spot.held:+.6g} / futuros {pos.fut.held:+.6g}",
                      "apertura")
        self.persist()

    def material(self, pos: ArbPosition) -> bool:
        """¿El descubierto supera la tolerancia y se puede operar (no es polvo)?"""
        res = pos.residual
        if abs(res) <= self.p.hedge_tol * max(abs(pos.spot.held), abs(pos.fut.held), 1e-12):
            return False
        return bool(self.spot.round_qty(pos.spot.symbol, abs(res)) if res > 0 else
                    self.fut.round_qty(pos.fut.symbol, -res)
                    or self.spot.round_qty(pos.spot.symbol, -res))

    def finish(self, pos: ArbPosition, status: str, why: str) -> None:
        pos.status, pos.exit_reason, pos.closed_at = status, why, self._clock()
        self._log(pos, f"{status.lower()}: {why}", "cierre" if status == CLOSED else "fallo")
        self.persist()

    # --- cierre y rebalanceo ----------------------------------------------------
    def close(self, pos: ArbPosition, reason: str, urgent: bool = False) -> bool:
        """Cierra ambas patas. True si quedó plano (salvo polvo bajo el mínimo de orden)."""
        if pos.status not in ACTIVE:
            return True
        prev = pos.status
        pos.status, pos.exit_reason = CLOSING, reason
        self._log(pos, f"cierre {'urgente ' if urgent else ''}pedido: {reason}", "orden")
        try:
            spot_q = self.spot.round_qty(pos.spot.symbol, max(0.0, min(
                pos.spot.held, self.spot.free(self.legs.base("spot", pos.spot.symbol)))))
            first, second = self.legs.ordered(pos, abs(pos.fut.held), False, spot_q)
            if first.qty > 0 and second.qty > 0:
                self._pair_close(pos, first, second, urgent, "cerrar")
            else:                                      # solo queda una pata
                self.legs.trim(pos, first if first.qty > 0 else second, "cerrar", urgent)
        except LegUnknown as e:
            pos.status = UNHEDGED
            self._log(pos, f"estado desconocido a mitad del cierre ({e})")
            self.persist()
            return False
        except BrokerError as e:
            pos.status = UNHEDGED if self.material(pos) or self._sent_unsettled(pos) else prev
            self._log(pos, f"cierre aplazado: {e}")
            self.persist()
            return False
        dust = (self.fut.round_qty(pos.fut.symbol, abs(pos.fut.held)) == 0
                and self.spot.round_qty(pos.spot.symbol, max(pos.spot.held, 0.0)) == 0)
        if dust:
            self.finish(pos, CLOSED, reason + (f" (polvo spot {pos.spot.held:.8g} bajo el "
                                                "mínimo)" if pos.spot.held else ""))
            return True
        pos.status = UNHEDGED if self.material(pos) else OPEN
        self._log(pos, "cierre aplazado: sigue cubierta y se reintenta" if pos.status == OPEN
                  else "cierre incompleto: la reconciliación corrige el descubierto")
        self.persist()
        return False

    def _pair_close(self, pos: ArbPosition, first: LegOrder, second: LegOrder, urgent: bool,
                    role: str) -> PairResult:
        if first.qty <= 0 and second.qty <= 0:
            return PairResult()
        r = self.legs.pair(pos, first, second, pos.max_leg_loss_bps, urgent,
                           roles=(role, role))
        for msg in r.issues:
            self._log(pos, msg)
        if r.over_cap:
            self.kill.activate(f"cierre de {pos.key}: pérdida al rehacer sobre el tope",
                               self._clock(), by="regla:pata")
        return r

    def rebalance(self, pos: ArbPosition, act: Action) -> None:
        """Añade margen libre al corto; si no alcanza, reduce ambas patas en `act.frac`."""
        try:
            avail = float(self.fut.account_summary()["available"])
            amount = math.ceil(act.margin_needed * 100) / 100       # céntimos de USDT
            if amount > 0 and avail >= amount:
                self.fut.add_margin(pos.fut.symbol, amount)
                pos.margin_added += amount
                pos.rebalances += 1
                self._log(pos, f"rebalanceo: +{amount:.2f} USDT de margen "
                          f"({act.reason})", "rebalanceo")
                self.persist()
                return
            q = self.fut.round_qty(pos.fut.symbol, abs(pos.fut.held) * act.frac)
            if q <= 0:
                self._log(pos, f"rebalanceo imposible (reducción bajo el mínimo): {act.reason}")
                return
            first, second = self.legs.ordered(pos, q, False)
            r = self._pair_close(pos, first, second, False, "rebalanceo")
        except LegUnknown as e:
            pos.status = UNHEDGED
            self._log(pos, f"estado desconocido en el rebalanceo ({e})")
        except BrokerError as e:
            if self.material(pos) or self._sent_unsettled(pos):
                pos.status = UNHEDGED
            self._log(pos, f"rebalanceo aplazado: {e}")
        else:
            done = r.second > 0 and not r.reversed
            pos.rebalances += int(done)
            self._log(pos, f"rebalanceo: ambas patas −{r.second:.6g} ({act.reason})" if done
                      else f"rebalanceo no hecho (se rehízo la primera pata): {act.reason}",
                      "rebalanceo")
        self.persist()

    def flatten_all(self, reason: str) -> bool:
        """Cierre urgente de todos los arbitrajes activos (kill-switch)."""
        flat = True
        for pos in self.active():
            if pos.status == CLOSING:
                pos.status = OPEN
            flat = self.close(pos, reason, urgent=True) and flat
        return flat
