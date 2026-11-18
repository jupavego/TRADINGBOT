"""Servicio continuo del bróker simulado (T48): ciclo en vivo por marco, latido y puesta al día.

Cada ciclo trae velas y funding nuevos, analiza las velas cerradas que falten en 15 m, 1 h y
4 h (contextos `vivo` si se deciden a lo sumo una vela después de su cierre) y escribe
`data/paper/heartbeat.json` para que el vigilante y la vista sepan que sigue en marcha.

Puesta al día automática (T182, reemplaza el botón «Reconstruir historial»; solo con «lo vivo
manda», `ExecParams.live_first_on`): tras cada ciclo, si en los últimos `CATCHUP_DAYS` días
quedan velas cerradas sin analizar (el equipo estuvo apagado más de lo que cubre el ciclo), el
servicio las analiza solo, en segundo plano, de a lotes y con prioridad baja. Esas velas no se
decidieron en tiempo real: quedan como `backtest` (reconstruidas), así que no entran en los libros
de los perfiles y en el aprendizaje solo pesan como opinión inicial acotada
(`eim/paper/prior.py`). Nadie tiene que lanzarla a mano.
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
from eim.operation.priority import lower_thread
from eim.paper.generate import closed_asofs, now_ms

WARMUP_BARS = 400                               # velas previas para los indicadores
LIVE_BARS = 48                                  # el ciclo rellena como mucho 48 velas por marco
FUNDING_LOOKBACK_MS = 30 * 86_400_000
FINE_BACKFILL_MS = 7 * 86_400_000                 # velas de 1 min del perfil de escalera
# El tramo vivo del 1 min se reescribe en cada vela nueva: cuando pasa de ~30 días, lo que tiene
# más de 7 se mueve al tramo histórico congelado (`Store.compact`), que nadie reescribe.
FINE_KEEP_MS = 7 * 86_400_000
FINE_COMPACT_ROWS = 30 * 1440
CATCHUP_DAYS = 30            # ventana que la puesta al día mantiene completa (velas cerradas)
CATCHUP_BATCH = 400          # velas como mucho por lote (≈ 10 min de CPU en un proceso)


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
    `symbols`, `poll_s`, `job`, `last_tick`, `live_error`, `hooks`, `catchup_tried`."""

    def _origin_for(self, tf: str):
        bar = tf_ms(tf)
        return lambda asof: "vivo" if now_ms() - asof <= 2 * bar else "backtest"

    # --- puesta al día automática (T182) ---------------------------------------------
    def _catchup_plan(self) -> list[tuple[str, str, list[int]]]:
        """Velas cerradas de la ventana que faltan por analizar (sin las que ya se intentaron en
        este proceso: si una no da contexto, por ejemplo por un hueco del almacén, no se repite
        cada minuto). Las más recientes van primero; como mucho `CATCHUP_BATCH` por lote. Las
        últimas `LIVE_BARS` son del ciclo en vivo: así nunca se calcula dos veces la misma vela ni
        se reetiqueta como reconstruida una que se decidió en vivo."""
        tried = self.catchup_tried
        plan, left = [], CATCHUP_BATCH
        for sym in self.symbols:
            for tf in self.tfs:
                b = self.store.bounds(sym, tf)
                if b is None or left <= 0:
                    continue
                n = int(CATCHUP_DAYS * 86_400_000 / tf_ms(tf))
                have = self.pstore.asofs(sym, tf)
                todo = [a for a in reversed(closed_asofs(b[1], tf_ms(tf), n)[:-LIVE_BARS])
                        if a not in have and (sym, tf, a) not in tried][:left]
                if todo:
                    plan.append((sym, tf, sorted(todo)))
                    left -= len(todo)
        return plan

    def catch_up(self) -> dict:
        """Lanza (si hace falta y no hay otro en curso) un lote de puesta al día en segundo
        plano. Solo con «lo vivo manda» (`ExecParams.live_first_on`): sin él (configuración de
        T31) lo reconstruido entra en los libros y rellenar huecos cambiaría la corrida."""
        if not self.ep.live_first_on(now_ms()) or self.job.state == "corriendo":
            return self.job.to_json()
        plan = self._catchup_plan()
        if not plan:
            return self.job.to_json()
        self.catchup_tried.update((sym, tf, a) for sym, tf, asofs in plan for a in asofs)
        syms = ",".join(dict.fromkeys(s for s, _, _ in plan))
        job = self.job = Job(state="corriendo", symbol=syms, started=now_ms(),
                             total=sum(len(a) for _, _, a in plan))

        def work() -> None:
            lower_thread()   # T128: trabajo de fondo; el ciclo en vivo y la API van primero
            base = 0
            try:
                for sym, tf, asofs in plan:
                    job.tf = tf

                    def prog(k: int, _total: int, base: int = base) -> None:
                        job.done = base + k
                    job.saved += self.gens[tf].run(self.pstore, sym, asofs, self._origin_for(tf),
                                                   job.stop, prog)
                    base += len(asofs)
                    if job.stop.is_set():
                        break
                job.state = "cancelado" if job.stop.is_set() else "terminado"
            except Exception as exc:  # el hilo nunca tumba la API
                job.state, job.error = "error", f"{type(exc).__name__}: {exc}"
            job.finished = now_ms()

        threading.Thread(target=work, name="eim-paper-catchup", daemon=True).start()
        return job.to_json()

    def stop_catchup(self) -> dict:
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
        try:
            self.catch_up()
        except Exception as exc:  # noqa: BLE001 - la puesta al día nunca frena el ciclo en vivo
            logging.getLogger("eim.paper").warning("puesta al día: %s: %s", type(exc).__name__, exc)
        return saved

    def _sync(self, sym: str) -> None:
        now = now_ms()
        fine = tuple(dict.fromkeys(p.fine_tf for p in self.profiles
                                   if p.fine_tf and sym in (p.symbols or (sym,))))
        for tf in dict.fromkeys((*self.tfs, self.ep.path_tf, *fine)):
            b = self.store.bounds(sym, tf)
            back = FINE_BACKFILL_MS if tf in fine else (WARMUP_BARS + LIVE_BARS) * tf_ms(tf)
            start = b[1] if b else now - back
            sync_candles(self.store, self.provider, sym, tf, start, now)
            if tf in fine:
                self.store.compact(sym, tf, FINE_KEEP_MS, FINE_COMPACT_ROWS)
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
        self.hooks.start()
        while True:
            try:
                await asyncio.to_thread(self.tick)
            except Exception as exc:  # red caída: se reintenta en el siguiente ciclo
                self.live_error = f"{type(exc).__name__}: {exc}"
                hooks_service.service_error("paper.broker", exc, mode=Mode.SIMULADO)
                self._beat(0)
            # T128: los ganchos (validación de 4 h, libro fijo, bots, setups) corren en su hilo,
            # a nivel batch y con su latido; el ciclo no los espera y late cada vuelta.
            self.hooks.kick()
            await asyncio.sleep(self.poll_s)
