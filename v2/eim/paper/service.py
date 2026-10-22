"""Servicio continuo del bróker simulado (T48): ciclo en vivo por marco, latido y backtest.

Cada ciclo trae velas y funding nuevos, analiza las velas cerradas que falten en 15 m, 1 h y
4 h (contextos `vivo` si se deciden a lo sumo una vela después de su cierre) y escribe
`data/paper/heartbeat.json` para que el vigilante y la vista sepan que sigue en marcha.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from eim.core import Mode
from eim.data.aggregate import aggregate_new
from eim.data.sync import sync_candles
from eim.data.timeframes import tf_ms
from eim.observability import hooks_service
from eim.paper.generate import closed_asofs, default_workers, now_ms

WARMUP_BARS = 400                               # velas previas para los indicadores
LIVE_BARS = 48                                  # el ciclo rellena como mucho 48 velas por marco
FUNDING_LOOKBACK_MS = 30 * 86_400_000
FINE_BACKFILL_MS = 7 * 86_400_000                 # velas de 1 min del perfil de escalera


@dataclass
class Job:
    state: str = "inactivo"     # inactivo | corriendo | terminado | cancelado | error
    symbol: str = ""
    tf: str = ""                # marco en curso
    done: int = 0
    total: int = 0
    saved: int = 0
    error: str = ""
    started: int | None = None
    finished: int | None = None
    stop: threading.Event = field(default_factory=threading.Event)

    def to_json(self) -> dict:
        return {k: getattr(self, k) for k in ("state", "symbol", "tf", "done", "total", "saved",
                                                "error", "started", "finished")}


class DeskService:
    """Mezcla para `PaperDesk`: espera `store`, `pstore`, `gens`, `tfs`, `ep`, `provider`,
    `symbols`, `poll_s`, `job`, `last_tick`, `live_error`, `after_tick`."""

    def _origin_for(self, tf: str):
        bar = tf_ms(tf)
        return lambda asof: "vivo" if now_ms() - asof <= 2 * bar else "backtest"

    # --- backtest ---------------------------------------------------------------------
    def start_backtest(self, symbol: str, days: float, step: int = 1,
                       tfs: tuple[str, ...] | None = None) -> dict:
        if self.job.state == "corriendo":
            return self.job.to_json()
        plan: list[tuple[str, list[int]]] = []
        for tf in tfs or self.tfs:
            b = self.store.bounds(symbol, tf)
            if b is None:
                continue
            n = max(1, int(days * 86_400_000 / tf_ms(tf) / step))
            plan.append((tf, closed_asofs(b[1], tf_ms(tf), n, step)))
        if not plan:
            raise LookupError(f"sin velas de {symbol} en {', '.join(tfs or self.tfs)}")
        job = self.job = Job(state="corriendo", symbol=symbol, started=now_ms(),
                             total=sum(len(a) for _, a in plan))

        def work() -> None:
            base = 0
            try:
                for tf, asofs in plan:
                    job.tf = tf

                    def prog(k: int, _total: int, base: int = base) -> None:
                        job.done = base + k
                    job.saved += self.gens[tf].run(self.pstore, symbol, asofs, self._origin_for(tf),
                                                   job.stop, prog, workers=default_workers())
                    base += len(asofs)
                    if job.stop.is_set():
                        break
                job.state = "cancelado" if job.stop.is_set() else "terminado"
            except Exception as exc:  # el hilo nunca tumba la API
                job.state, job.error = "error", f"{type(exc).__name__}: {exc}"
            job.finished = now_ms()

        threading.Thread(target=work, name="eim-paper-backtest", daemon=True).start()
        return job.to_json()

    def stop_backtest(self) -> dict:
        self.job.stop.set()
        return self.job.to_json()

    # --- servicio en vivo -------------------------------------------------------------
    def tick(self) -> int:
        """Trae datos nuevos (si hay proveedor) y analiza las velas cerradas que falten."""
        saved = 0
        for sym in self.symbols:
            if self.provider is not None:
                self._sync(sym)
            for tf in self.tfs:
                b = self.store.bounds(sym, tf)
                if b is None:
                    continue
                saved += self.gens[tf].run(self.pstore, sym,
                                           closed_asofs(b[1], tf_ms(tf), LIVE_BARS),
                                           self._origin_for(tf))
        self.last_tick, self.live_error = now_ms(), ""
        self._beat(saved)
        return saved

    def _sync(self, sym: str) -> None:
        now = now_ms()
        fine = tuple(dict.fromkeys(p.ladder.fine_tf for p in self.profiles
                                   if p.ladder and sym in (p.symbols or (sym,))))
        for tf in dict.fromkeys((*self.tfs, self.ep.path_tf, *fine)):
            b = self.store.bounds(sym, tf)
            back = FINE_BACKFILL_MS if tf in fine else (WARMUP_BARS + LIVE_BARS) * tf_ms(tf)
            start = b[1] if b else now - back
            sync_candles(self.store, self.provider, sym, tf, start, now)
        self._keep_5m(sym)
        f = self.store.read_series("funding", sym, last=1)
        rates = self.provider.funding_rates(sym, f[-1][0] + 1 if f else now - FUNDING_LOOKBACK_MS,
                                            now)
        if rates:
            self.store.upsert_series("funding", sym, "-", rates, self.provider.name)

    def _keep_5m(self, sym: str) -> None:
        """Mantiene al día el marco 5m (solo de almacén; lo usa NFI) agregándolo del 1m recién
        sincronizado. Solo si el 5m ya existe (se crea con `eim.bots.backfill`); nunca frena el
        ciclo."""
        if self.store.bounds(sym, "5m") is None or self.store.bounds(sym, "1m") is None:
            return
        try:
            aggregate_new(self.store, sym)
        except Exception as e:  # noqa: BLE001
            logging.getLogger("eim.paper").warning("5m %s: %s: %s", sym, type(e).__name__, e)

    def heartbeat_path(self) -> Path:
        return Path(self.store.root) / "paper" / "heartbeat.json"

    def _beat(self, saved: int) -> None:
        last = {f"{s}:{tf}": self.pstore.stamp(s, tf)[1] for s in self.symbols for tf in self.tfs}
        try:
            p = self.heartbeat_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"last_tick": self.last_tick, "saved": saved,
                                     "error": self.live_error, "last_context": last}),
                         encoding="utf-8")
            hooks_service.beat("paper.broker", mode=Mode.SIMULADO,
                               status="degraded" if self.live_error else "ok",
                               detail={"saved": saved, "error": self.live_error[:120]})
        except OSError:
            pass   # el latido nunca tumba el ciclo

    async def loop(self) -> None:
        self.loop_started = now_ms()
        while True:
            try:
                await asyncio.to_thread(self.tick)
            except Exception as exc:  # red caída: se reintenta en el siguiente ciclo
                self.live_error = f"{type(exc).__name__}: {exc}"
                hooks_service.service_error("paper.broker", exc, mode=Mode.SIMULADO)
                self._beat(0)
            for hook in self.after_tick:   # p. ej. la validación al cierre de cada vela de 4 h
                try:
                    await asyncio.to_thread(hook)
                except Exception as exc:  # un gancho nunca detiene el servicio
                    self.live_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(self.poll_s)
