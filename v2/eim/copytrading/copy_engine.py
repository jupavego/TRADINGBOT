"""Motor de copia simulada (T42): una subcuenta virtual que copia a UN líder. Modo SIMULADO.

Señal (ejecuciones del líder) → replicador → riesgo T29 (solo lo que aumenta riesgo) →
orden simulada al precio del seguidor (cotización grabada o supuesto declarado) con comisión
de tomador → bitácora. Con cada marca: stop de protección, capital y kill-switch propio
(caída ≥ límite → cierre ordenado). Funding horario con la posición de esa hora.
Reconciliación contra la foto real del líder: divergencia no explicada en `recon_confirm`
comprobaciones seguidas → pausa + alerta; nunca se «arregla» operando. Mismo código en vivo
(servicio de líderes) y sobre el historial (reproducción): mismo flujo → mismo resultado.
"""

from __future__ import annotations

from collections.abc import Callable

from eim.copytrading.copy_book import Account, ClosedTrip
from eim.copytrading.copy_control import EngineControl
from eim.copytrading.copy_models import CopyFill, ExecQuote, JournalEntry, Signal
from eim.copytrading.copy_params import CopyParams, ExchangeSpec
from eim.copytrading.copy_recon import Recon
from eim.copytrading.copy_risk import CopyRisk
from eim.copytrading.copy_state import EngineState
from eim.copytrading.replicator import Action, CoinCopy, Ctx, decide, sgn
from eim.core.leaders import LeaderPosition
from eim.risk import RiskConfig, RiskDecision

SIDE = {1: "compra", -1: "venta"}


class CopyEngine(EngineControl, EngineState):
    def __init__(self, leader_id: str, p: CopyParams, spec: ExchangeSpec, risk_cfg: RiskConfig,
                 *, t0: int, label: str = "", measure: bool = False,
                 on_entry: Callable[[JournalEntry], None] | None = None,
                 on_alert: Callable[[str, str, str], None] | None = None,
                 keep: int | None = None) -> None:
        self.leader_id, self.label, self.p, self.spec = leader_id, label, p, spec
        self.measure = measure  # líder sin aprobar: se simula solo para medir
        self.approved = True  # en modo «approved» lo fija el conductor con el veredicto
        self.account = Account(p.initial_equity, t0)
        self.coins: dict[str, CoinCopy] = {}
        self.risk = CopyRisk(risk_cfg, p, sink=self._on_risk)
        self.leader_av: float | None = None
        self.feed_t: int | None = None
        self.feed_down: int | None = None
        self.paused: str | None = None
        self.resync = False  # tras reanudar a mano: adoptar la foto real del líder
        self.gap: tuple[int, int] | None = None  # hueco de captura pendiente de resincronizar
        self.last_sig_t: dict[str, int] = {}  # hora del exchange de la última señal por moneda
        self.started_t = self.state_t = t0  # state_t: hora del exchange de la foto inicial
        self.seen: dict[str, None] = {}
        self.seq = 0
        self.counts: dict[str, int] = {}
        self.mismatch: dict[str, int] = {}
        self.trip_info: dict[str, dict] = {}
        self.last_recon: Recon | None = None
        self.last_bad_t: int | None = None  # última reconciliación con diferencia no explicada
        self.fills: list[CopyFill] = []
        self.closed: list[ClosedTrip] = []  # viajes propios terminados (neto con funding)
        self.journal: list[JournalEntry] = []
        self.keep = keep  # None: se guarda todo (reproducción); en vivo, la cola
        self.on_entry, self.on_alert = on_entry, on_alert
        self._now = t0

    # --- bitácora -----------------------------------------------------------------------------
    def log(self, what: str, text: str, coin: str = "", code: str = "", **data) -> None:
        self.seq += 1
        e = JournalEntry(leader_id=self.leader_id, seq=self.seq, t=self._now, kind=what,
                         coin=coin, code=code, text=text, data=data)
        self.journal.append(e)
        if self.keep is not None:
            del self.journal[:-self.keep]
        if self.on_entry:
            self.on_entry(e)

    def _count(self, key: str) -> None:
        self.counts[key] = self.counts.get(key, 0) + 1

    def _on_risk(self, d: RiskDecision) -> None:
        self.log("risk", ("aprobado: máx. " + f"{d.size:.6g}") if d.approved else
                 "vetado: " + "; ".join(d.reasons), coin=d.symbol,
                 code="aprobado" if d.approved else "vetado", plan_id=d.plan_id,
                 config=d.config_version, reasons=list(d.reasons), size=d.size)

    def _alert(self, level: str, title: str, detail: str) -> None:
        if self.on_alert:
            self.on_alert(level, title, detail)

    # --- arranque y flujo ---------------------------------------------------------------------
    def start(self, t: int, positions: list[LeaderPosition], state_t: int | None = None) -> None:
        """Foto inicial (`t` = cuando la vimos, `state_t` = hora del estado en el exchange):
        lo ya abierto es preexistente (no se copia salvo decisión explícita)."""
        self._now, self.state_t = t, state_t if state_t is not None else t
        for x in positions:
            signed = x.size if x.side == "long" else -x.size
            self.coins[x.symbol] = CoinCopy(
                x.symbol, leader=signed, leader_entry=x.entry, trip_t=t,
                excluded=None if self.p.copy_existing else "preexistente")
        how = "se copian desde su próximo cambio" if self.p.copy_existing else "no se copian"
        self.log("start", f"empieza a seguir a {self.label or self.leader_id}: "
                 f"{len(positions)} posiciones preexistentes ({how})",
                 coins=sorted(x.symbol for x in positions), equity=self.account.equity(),
                 measure=self.measure)

    def confirm_feed(self, t: int) -> None:
        if self.feed_t is not None and t - self.feed_t > self.p.recon_gap_ms:
            self.gap = (self.feed_t, t)  # sin confirmar el flujo: lo cambiado no se vio
        self.feed_t = max(self.feed_t or 0, t)

    def set_feed_down(self, t: int | None) -> None:
        self.feed_down = t

    def _gate(self) -> tuple[str, str] | None:
        if self.paused:
            return "pausa", f"copia en pausa: {self.paused}"
        if self.risk.kill.active:
            return "kill", f"kill-switch de la subcuenta: {self.risk.kill.state()['reason']}"
        if self.feed_down is not None:
            return "flujo_caido", "flujo en vivo del líder caído: no se abren posiciones"
        if not self.approved:
            return "no_aprobado", "líder no aprobado por el scorecard (T41)"
        return None

    # --- señales ------------------------------------------------------------------------------
    def on_signal(self, sig: Signal, quote: ExecQuote | None, now: int) -> list[CopyFill]:
        keys = [f"{tid}:{oid}" for tid, oid in sig.keys]
        if sig.t <= self.state_t or all(k in self.seen for k in keys):
            return []  # ya reflejada en la foto inicial, o repetida
        for k in keys:
            self.seen[k] = None
        if len(self.seen) > 20_000:
            self.seen = dict.fromkeys(list(self.seen)[-10_000:])
        self._now = max(self._now, now)  # la bitácora nunca retrocede
        coin, acc = sig.coin, self.account
        if sig.t < self.last_sig_t.get(coin, 0):
            # tras un corte, el reenvío del WS (lo más nuevo) puede llegar antes que el relleno
            # REST (lo más viejo): lo anterior a lo ya procesado no cambia la posición actual
            self._count("stale")
            self.log("signal", f"ejecuciones de {coin} anteriores a la última procesada (llegaron "
                     f"tarde, {sig.channel}): historial, no cambian la posición", coin=coin,
                     code="historial", t_leader=sig.t, start=sig.start, end=sig.end)
            return []
        self.account.roll(now)
        self._count("signals")
        self.last_sig_t[coin] = sig.t
        self.log("signal", f"líder {sig.start:+.6g} → {sig.end:+.6g} {coin} a {sig.vwap:,.6g} "
                 f"(latencia {sig.latency_ms} ms, {sig.channel})", coin=coin,
                 code=sig.channel, t_leader=sig.t, start=sig.start, end=sig.end,
                 vwap=sig.vwap, fills=sig.fills, latency_ms=sig.latency_ms)
        ctx = Ctx(t=now, equity=acc.equity(), leader_av=self.leader_av, quote=quote,
                  other_notional=acc.notional(exclude=coin))
        c = self.coins.get(coin) or CoinCopy(coin)
        d, c2 = decide(c, acc.size(coin), sig, ctx, self.p, self.spec)
        if d.new_trip and c2.trip_t is not None:
            self.trip_info[f"{coin}:{c2.trip_t}"] = {
                "coin": coin, "trip_t": c2.trip_t, "ratio": c2.ratio, "copied": False,
                "excluded": c2.excluded, "skips": [], "leader_entry": c2.leader_entry}
            if len(self.trip_info) > 2_000:
                self.trip_info = dict(list(self.trip_info.items())[-1_000:])
        info = self.trip_info.get(f"{coin}:{c2.trip_t}")
        if info is not None and info.get("ratio") is None:
            info["ratio"] = c2.ratio
        self.log("decision", self._describe(d.actions) or "sin orden", coin=coin,
                 code=",".join(a.kind for a in d.actions) or "ninguna", target=d.target,
                 ratio=d.ratio, note=d.note, own=acc.size(coin))
        note = d.note
        for s in d.skips:
            self._reject(coin, s.code, s.text, info)
        fills = []
        for a in d.actions:
            if a.grows:
                a, why = self._admit(a, sig, quote, now, info)
                if a is None:
                    note = why
                    continue
                if why:
                    note = why
            held = acc.positions.get(coin)
            trip = c2.trip_t if a.grows or held is None else held.trip_t
            fills.append(self._execute(a, sig, quote, now, trip))
            if a.grows and info is not None:
                info["copied"] = True
        c2.note = note
        if c2.leader == 0 and acc.size(coin) == 0:
            self.coins.pop(coin, None)
        else:
            self.coins[coin] = c2
        self._after(now)
        return fills

    def _reject(self, coin: str, code: str, text: str, info: dict | None) -> None:
        self._count(f"rechazo:{code.split(':')[0]}")
        self.log("reject", text, coin=coin, code=code)
        if info is not None:
            info["skips"].append(code)

    def _admit(self, a: Action, sig: Signal, quote: ExecQuote | None, now: int,
               info: dict | None) -> tuple[Action | None, str | None]:
        """Puerta de lo que aumenta riesgo: pausa/kill/flujo/aprobación y motor T29."""
        gate = self._gate()
        if gate:
            self._reject(a.coin, gate[0], gate[1], info)
            return None, gate[1]
        price = quote.price(a.side, self.p.half_spread)  # el replicador exige cotización
        own = abs(self.account.size(a.coin))
        rd = self.risk.check(plan_id=f"{self.leader_id}:{a.coin}:{sig.t}:{sig.last_key[0]}",
                             coin=a.coin, side=a.side, price=price, signal_t=sig.t, now=now,
                             feed_t=self.feed_t, acc=self.account,
                             source=f"copia simulada {self.leader_id}")
        if not rd.approved:
            text = "motor de riesgo: " + "; ".join(rd.reasons)
            self._reject(a.coin, "riesgo", text, info)
            return None, text
        if abs(a.target) <= rd.size + 1e-12:
            return a, None
        qty = self.spec.round_down(a.coin, rd.size - own)
        why = f"tope del motor de riesgo: posición ≤ {rd.size:.6g} ({rd.config_version})"
        if qty <= 0 or qty * quote.mid < self.spec.min_notional:
            self._reject(a.coin, "riesgo_tamano", why, info)
            return None, why
        return a.model_copy(update={"qty": qty, "target": a.side * (own + qty),
                                    "notes": (*a.notes, why)}), why

    def _execute(self, a: Action, sig: Signal | None, quote: ExecQuote | None, now: int,
                 trip_t: int | None, kind: str | None = None) -> CopyFill:
        acc, hs = self.account, self.p.half_spread
        if quote is not None:
            px, mid, src = quote.price(a.side, hs), quote.mid, quote.src
        elif acc.mark(a.coin) is not None:
            mid, src = acc.mark(a.coin), "marca"
            px = mid * (1 + hs * a.side)
        else:
            mid, src = None, "lider"
            px = sig.vwap * (1 + hs * a.side)
        fee = a.qty * px * self.p.taker_fee
        realized, closed = acc.fill(a.coin, a.side, a.qty, px, fee, now, trip_t)
        if closed is not None:
            self.closed.append(closed)
            if self.keep is not None:
                del self.closed[:-self.keep]
        pos = acc.positions.get(a.coin)
        if pos is not None:
            pos.stop = pos.entry * (1 - sgn(pos.size) * self.p.stop_frac)
        if a.coin not in acc.marks or quote is not None:
            acc.set_mark(a.coin, now, mid or px)
        cf = CopyFill(leader_id=self.leader_id, coin=a.coin, t=now, kind=kind or a.kind,
                      side=a.side, qty=a.qty, price=px, mid=mid,
                      leader_px=sig.vwap if sig else None, fee=fee, realized=realized, src=src,
                      trip_t=trip_t, signal_t=sig.t if sig else None,
                      latency_ms=now - sig.t if sig else None)
        self.fills.append(cf)
        if self.keep is not None:
            del self.fills[:-self.keep]
        self._count("orders")
        self.log("order", f"{SIDE[a.side]} {a.qty:.6g} {a.coin} a {px:,.6g} ({src}) · "
                 f"comisión {fee:,.2f} USD" + (f" · PnL {realized:+,.2f}" if realized else ""),
                 coin=a.coin, code=cf.kind, **cf.model_dump(exclude={"leader_id", "coin"}))
        return cf

    @staticmethod
    def _describe(actions: list[Action]) -> str:
        return "; ".join(f"{a.kind} {SIDE[a.side]} {a.qty:.6g} → {a.target:+.6g}"
                         for a in actions)

    # --- marcas, funding, kill ----------------------------------------------------------------
    def on_mark(self, coin: str, t: int, px: float, low: float | None = None,
                high: float | None = None, open_: float | None = None) -> CopyFill | None:
        self._now = max(self._now, t)
        acc = self.account
        acc.set_mark(coin, t, px)
        pos, out = acc.positions.get(coin), None
        if pos is not None and pos.stop is not None:
            side = sgn(pos.size)
            lo, hi = (low if low is not None else px), (high if high is not None else px)
            if (lo <= pos.stop) if side > 0 else (hi >= pos.stop):
                o = open_ if open_ is not None else px
                trigger = min(o, pos.stop) if side > 0 else max(o, pos.stop)
                q = ExecQuote(t=t, at=t, mid=trigger, src="marca")
                out = self._exit(coin, "stop", q, t,
                                 f"stop de protección {pos.stop:,.6g} tocado ({trigger:,.6g})")
        acc.roll(t)
        acc.sample(t)
        self._after(t)
        return out

    def _exit(self, coin: str, why: str, quote: ExecQuote, t: int, text: str) -> CopyFill:
        pos = self.account.positions[coin]
        a = Action(coin=coin, kind="close", side=-sgn(pos.size), qty=abs(pos.size), target=0.0)
        self.log(why, text, coin=coin, code=why)
        cf = self._execute(a, None, quote, t, pos.trip_t, kind=why)
        c = self.coins.get(coin)
        if c is not None and c.leader != 0:
            c.excluded, c.note = why, text
        return cf
