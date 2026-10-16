"""Copia simulada EN VIVO (T42) dentro del servicio de líderes. Modo SIMULADO, saldo virtual.

Una subcuenta (`CopyEngine`) por líder capturado. El servicio le pasa lo que ya recibe:
- ejecuciones (`on_fills`) → señales en cola por (líder, moneda), en orden. Las vistas en
  vivo esperan su cotización del seguidor (`on_quotes`, `FollowQuote` de T41 = bid/ask a los
  300 ms); si no llega en `pending_timeout_ms`, o la señal es tardía (relleno REST, reenvío
  del WS), se ejecuta con la cotización vigente (`price_now`: `bbo` o `allMids`).
- marcas (`on_mark`: `bbo`/`allMids`) → stops, capital y kill-switch de la subcuenta.
- reconciliaciones T40 (`on_recon`, cada 30 s) → la primera arranca la subcuenta con la foto
  (lo abierto es preexistente); las siguientes confirman el flujo y reconcilian.
- WS caído/vuelto (`feed_down`/`feed_up`) → no se abre nada mientras el flujo está caído.
- `tick` (cada segundo): vence colas, funding nuevo (de `leader_funding`), estado de
  aprobación y valor de cuenta, bitácora a la base, estado cada minuto, resumen JSON
  (`data/leaders/copy_sim.json`) cada 10 s y reanudaciones pedidas a mano.
Modo (`EIM_COPY_SIM`): `tracked` (todos los capturados, como medición: ninguno está aprobado
todavía), `approved` (solo abre con líderes aprobados) u `off`.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from eim.copytrading.copy_engine import CopyEngine
from eim.copytrading.copy_models import MODE, ExecQuote, JournalEntry, Signal, group_fills
from eim.copytrading.copy_params import CopyParams, ExchangeSpec
from eim.copytrading.portfolio import account_values
from eim.core.leaders import FollowQuote, Leader, LeaderFill, LeaderPosition
from eim.data.copy_store import take_control, write_summary
from eim.risk import RiskConfig

LIVE_MAX_LATENCY_MS = 120_000  # como `QuoteBook.expect`: más tarde no espera cotización
SAVE_EVERY_MS = 60_000
EXPORT_EVERY_MS = 10_000
REFRESH_EVERY_MS = 60_000
CATCHUP_MARGIN_MS = 120_000  # relectura tras reiniciar: desde un poco antes del último guardado
log = logging.getLogger(__name__)


@dataclass
class _Queued:
    sig: Signal
    live: bool
    due: int  # sin cotización a esta hora: se ejecuta con la vigente
    quote: FollowQuote | None = None


@dataclass
class _Lane:
    items: deque[_Queued] = field(default_factory=deque)


class CopyLive:
    def __init__(self, store, root: str | Path, p: CopyParams, spec: ExchangeSpec,
                 risk_cfg: RiskConfig, leaders: list[Leader], *, mode: str = "tracked",
                 price_now: Callable[[str, int], ExecQuote | None] | None = None,
                 alert: Callable[[str, str, str], None] | None = None) -> None:
        self.store, self.root, self.p, self.spec = store, Path(root), p, spec
        self.risk_cfg, self.mode = risk_cfg, mode
        self.price_now = price_now or (lambda coin, now: None)
        self.alert = alert
        self.status = {ld.id: ld for ld in leaders}
        self.engines: dict[str, CopyEngine] = {}
        self.lanes: dict[tuple[str, str], _Lane] = {}
        self.by_key: dict[tuple[str, int, int], _Queued] = {}
        self.buffer: list[JournalEntry] = []
        self.funding_seen = 0
        self._next = {"save": 0, "export": 0, "refresh": 0}
        saved = store.copy_states()
        for ld in leaders:
            if ld.id in saved:
                eng = self._engine(ld, 0)
                eng.load_state(saved[ld.id])
                self._apply_status(eng)
        # Lo procesado entre el último guardado y una caída se perdió con el proceso, y T40 solo
        # re-entrega lo posterior a su última ejecución GUARDADA: se relee de la base.
        self._catchup = {lid: e._now for lid, e in self.engines.items()}
        if saved:
            log.info("copia simulada: %d subcuentas restauradas", len(self.engines))

    # --- subcuentas ---------------------------------------------------------------------------
    def _engine(self, ld: Leader, t0: int) -> CopyEngine:
        eng = CopyEngine(ld.id, self.p, self.spec, self.risk_cfg, t0=t0, label=ld.label,
                         on_entry=self.buffer.append, on_alert=self._alert, keep=200)
        self.engines[ld.id] = eng
        self._apply_status(eng)
        return eng

    def _apply_status(self, eng: CopyEngine) -> None:
        st = self.status.get(eng.leader_id)
        approved = st is not None and st.status == "approved"
        eng.measure = self.mode == "tracked" and not approved
        eng.approved = approved or self.mode == "tracked"

    def _alert(self, level: str, title: str, detail: str) -> None:
        log.warning("%s: %s", title, detail)
        if self.alert:
            self.alert(level, title, detail)

    # --- entradas del servicio ----------------------------------------------------------------
    def on_fills(self, fills: list[LeaderFill], now: int) -> None:
        if self._catchup:
            self._catch_up(now)
        for sig in group_fills(fills):
            eng = self.engines.get(sig.leader_id)
            if eng is None or sig.t <= eng.state_t:
                continue  # aún sin foto inicial, o ya reflejada en ella
            live = sig.channel != "ws_snapshot" and 0 <= sig.latency_ms <= LIVE_MAX_LATENCY_MS
            q = _Queued(sig, live, sig.observed_at + self.p.exec_delay_ms +
                        self.p.pending_timeout_ms)
            self.lanes.setdefault((sig.leader_id, sig.coin), _Lane()).items.append(q)
            if live:
                self.by_key[(sig.leader_id, *sig.last_key)] = q
        self.drain(now)

    def on_quotes(self, quotes: list[FollowQuote], now: int) -> None:
        for fq in quotes:
            q = self.by_key.pop((fq.leader_id, fq.tid, fq.oid), None)
            if q is not None:
                q.quote = fq
        self.drain(now)

    def drain(self, now: int) -> None:
        for (lid, coin), lane in list(self.lanes.items()):
            eng = self.engines.get(lid)
            if eng is None:
                del self.lanes[(lid, coin)]
                continue
            while lane.items:
                q = lane.items[0]
                if q.live and q.quote is None and now < q.due:
                    break
                lane.items.popleft()
                self.by_key.pop((lid, *q.sig.last_key), None)
                at = q.sig.observed_at + self.p.exec_delay_ms
                if q.quote is not None and q.quote.follow_at - q.quote.quote_t <= \
                        self.p.quote_timeout_ms:
                    fq = q.quote
                    quote = ExecQuote(t=fq.quote_t, at=fq.follow_at, mid=fq.mid, bid=fq.bid,
                                      ask=fq.ask, src=fq.src)
                else:
                    quote, at = self.price_now(coin, now), max(at, now)
                eng.on_signal(q.sig, quote, at)
            if not lane.items:
                del self.lanes[(lid, coin)]

    def coins(self) -> set[str]:
        """Monedas que alguna subcuenta tiene o sigue (las únicas que necesitan marca)."""
        out: set[str] = set()
        for e in self.engines.values():
            out |= set(e.account.positions) | set(e.coins)
        return out

    def pending(self, lid: str) -> set[str]:
        return {coin for (x, coin), lane in self.lanes.items() if x == lid and lane.items}

    def on_mark(self, coin: str, t: int, mid: float) -> None:
        for eng in self.engines.values():
            if coin in eng.account.positions or coin in eng.coins:
                eng.on_mark(coin, t, mid)

    def on_recon(self, ld: Leader, t_state: int, obs: int,
                 positions: list[LeaderPosition]) -> None:
        if self._catchup:
            self._catch_up(obs)
        eng = self.engines.get(ld.id)
        if eng is None:
            eng = self._engine(ld, obs)
            eng.leader_av = self._av(ld.id)
            eng.confirm_feed(obs)
            eng.start(obs, positions, state_t=t_state)
            return
        eng.confirm_feed(obs)
        photo = {x.symbol: x.size if x.side == "long" else -x.size for x in positions}
        eng.reconcile(obs, photo, self.pending(ld.id), state_t=t_state)

    def feed_down(self, lids: list[str], since: int) -> None:
        for lid in lids:
            if lid in self.engines:
                self.engines[lid].set_feed_down(since)

    def feed_up(self, lids: list[str]) -> None:
        for lid in lids:
            if lid in self.engines:
                self.engines[lid].set_feed_down(None)

    # --- tareas periódicas --------------------------------------------------------------------
    def _av(self, lid: str) -> float | None:
        pf = self.store.portfolio(lid)
        avs = account_values(pf[1] if pf else None)
        return avs[-1][1] if avs else None

    def _funding(self) -> None:
        rows = self.store.query(
            "SELECT symbol, t, usdc, rate, size, observed_at FROM leader_funding WHERE "
            "observed_at > ? ORDER BY observed_at", [self.funding_seen])
        for coin, t, usdc, rate, size, obs in rows:
            self.funding_seen = max(self.funding_seen, obs)
            if not rate or not size or usdc / (-size * rate) <= 0:
                continue
            px, h = usdc / (-size * rate), t - t % 3_600_000
            for eng in self.engines.values():
                if eng.account.size_at(coin, h):
                    eng.on_funding(coin, h, rate, px)

    def _refresh(self) -> None:
        self.status = {ld.id: ld for ld in self.store.leaders()}
        for lid, eng in self.engines.items():
            self._apply_status(eng)
            eng.leader_av = self._av(lid) or eng.leader_av
        ctl = take_control(self.root)
        for lid in (ctl or {}).get("resume") or []:
            if lid in self.engines:
                self.engines[lid].resume(int(ctl.get("requested_at") or 0), by="manual (CLI)")

    def _catch_up(self, now: int) -> None:
        """Antes del primer evento tras restaurar (T40 puede reconciliar antes de la primera
        vuelta de tareas): relee lo posterior al último guardado de cada subcuenta."""
        pending, self._catchup = self._catchup, {}
        n = 0
        for lid, since in pending.items():
            fills = self.store.fills(lid, start=since - CATCHUP_MARGIN_MS)
            n += len(fills)
            if fills:
                self.on_fills(fills, now)  # tardías: la deduplicación descarta lo ya visto
        log.info("copia simulada: %d ejecuciones releídas tras el reinicio", n)

    def tick(self, now: int) -> None:
        if self._catchup:
            self._catch_up(now)
        self.drain(now)
        if now >= self._next["refresh"]:
            self._next["refresh"] = now + REFRESH_EVERY_MS
            if self.funding_seen == 0:  # al arrancar, solo lo de las últimas 2 h
                self.funding_seen = now - 2 * 3_600_000
            self._funding()
            self._refresh()
        self.flush()
        if now >= self._next["save"]:
            self._next["save"] = now + SAVE_EVERY_MS
            self.save(now)
        if now >= self._next["export"]:
            self._next["export"] = now + EXPORT_EVERY_MS
            self.export(now)

    def flush(self) -> None:
        if self.buffer:
            batch, self.buffer = self.buffer, []
            self.store.add_journal(batch)

    def save(self, now: int) -> None:
        self.flush()
        for lid, eng in self.engines.items():
            self.store.save_copy_state(lid, now, eng.to_state())

    def export(self, now: int) -> None:
        accounts = [e.summary() for e in self.engines.values()]
        write_summary(self.root, {
            "type": "copy_sim", "mode": MODE, "sim_mode": self.mode, "asof": now,
            "label": "Simulación: saldo virtual, sin órdenes reales ni de testnet",
            "params": self.p.summary(), "risk_version": self.risk_cfg.version,
            "exchange": {"venue": self.spec.venue, "source": self.spec.source,
                         "min_notional": self.spec.min_notional},
            "accounts": sorted(accounts, key=lambda a: -a["equity"]),
            "pending": sum(len(lane.items) for lane in self.lanes.values())})

    def close(self, now: int) -> None:
        self.drain(now + self.p.pending_timeout_ms + self.p.exec_delay_ms)
        self.save(now)
        self.export(now)
